"""
PDF financial table extractor using Claude Vision API.

Extraction strategy
-------------------
1. Convert all PDF pages to PNG images with pdf2image (DPI 150).
2. For each page, send the image to Claude Vision with a structured JSON
   extraction prompt.
3. Claude returns {section, rows: [{label, amount_n, amount_n1}]} or null.
4. Aggregate rows by section across all pages, mapping amount_n → exercice_n.
5. Cache result in-process by SHA-256 of the raw PDF bytes.

Returned structure (interface unchanged — reconciliation.py unaffected)
-----------------------------------------------------------------------
{
  "bilan_actif": {
      "rows": [{"label": str, "exercice_n": float|None, "exercice_n1": float|None}, ...],
      "confidence": 1.0,
      "source": "vision"
  },
  "bilan_passif":       { ... },
  "compte_de_resultat": { ... },
}
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import anthropic
from pdf2image import convert_from_bytes

# ---------------------------------------------------------------------------
# sys.path — allow importing app.config from the parsers/ sub-package
# ---------------------------------------------------------------------------

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.config import settings  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL = "claude-sonnet-4-6"
_DPI   = 150

_SYSTEM_PROMPT = (
    "You are a French accounting expert extracting financial data from annual reports."
)

_USER_PROMPT = """\
Extract all financial tables from this page.
If this page contains a Bilan Actif, Bilan Passif, or Compte de résultat table, return a JSON object:
{
  "section": "bilan_actif" | "bilan_passif" | "compte_de_resultat" | null,
  "rows": [
    {"label": "Créances clients et comptes rattachés", "amount_n": 16929907, "amount_n1": 14070260}
  ]
}
Rules:
- Skip ALL CAPS rows (section totals like ACTIF IMMOBILISE, TOTAL GENERAL)
- Only extract rows that have at least one numeric value
- Use the most recent year column (leftmost numeric column after label) as amount_n
- Return null if no financial table on this page
- Return ONLY valid JSON, no explanation
"""

_VALID_SECTIONS = frozenset({"bilan_actif", "bilan_passif", "compte_de_resultat"})


# ---------------------------------------------------------------------------
# In-process caches (SHA-256 keyed)
# ---------------------------------------------------------------------------

_EXTRACTION_CACHE:  dict[str, dict] = {}   # sha256 → sections result
_PAGE_COUNT_CACHE:  dict[str, int]  = {}   # sha256 → page count


# ---------------------------------------------------------------------------
# Anthropic client (lazy singleton)
# ---------------------------------------------------------------------------

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_total_row(label: str) -> bool:
    """
    Return True for ALL-CAPS labels — section totals that must not be reconciled.
    Examples: "ACTIF IMMOBILISE", "TOTAL GENERAL", "CAPITAUX PROPRES".
    Secondary safety net on top of Claude's own skip instruction.
    """
    alpha = [c for c in label if c.isalpha()]
    return len(alpha) >= 3 and all(c.isupper() for c in alpha)


def _to_float(v: object) -> float | None:
    """Coerce a JSON value to float, returning None on failure."""
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_claude_json(text: str) -> dict | None:
    """
    Parse a Claude response that should be a JSON object.

    Handles:
    - Plain JSON
    - Markdown code fences: ```json … ```
    - Literal "null" response (no financial table on page)

    Returns the parsed dict, or None when no financial table is present.
    """
    text = text.strip()

    # Strip optional markdown code fence
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    if not text or text.lower() == "null":
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Attempt to salvage a JSON object embedded in prose
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            logger.debug("Could not parse Claude response as JSON: %.120s", text)
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None
    if data.get("section") not in _VALID_SECTIONS:
        return None  # null section or unrecognised section

    return data


# ---------------------------------------------------------------------------
# Single-page Vision call
# ---------------------------------------------------------------------------

def _process_page(image_b64: str, page_num: int) -> dict | None:
    """
    Send one page image to Claude Vision and return the parsed JSON,
    or None if no financial table is found on this page.
    """
    client = _get_client()

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": _USER_PROMPT,
                    },
                ],
            }],
        )
    except anthropic.APIError as exc:
        logger.error("Claude Vision API error on page %d: %s", page_num, exc)
        return None

    raw_text = response.content[0].text if response.content else ""
    return _parse_claude_json(raw_text)


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_plaquette_data(pdf_bytes: bytes) -> dict[str, dict]:
    """
    Extract financial tables from a PDF plaquette using Claude Vision.

    Pages are processed sequentially.  Results are cached in-process by
    SHA-256 so repeated calls with the same PDF skip the Vision API calls.

    Returns
    -------
    dict with keys "bilan_actif", "bilan_passif", "compte_de_resultat"
    (absent if not found).  Each value::

        {
            "rows":       [{"label": str, "exercice_n": float|None, "exercice_n1": float|None}],
            "confidence": 1.0,
            "source":     "vision",
        }
    """
    cache_key = hashlib.sha256(pdf_bytes).hexdigest()
    if cache_key in _EXTRACTION_CACHE:
        return _EXTRACTION_CACHE[cache_key]

    # ── Convert PDF to page images ────────────────────────────────────────────
    try:
        images = convert_from_bytes(pdf_bytes, dpi=_DPI)
    except Exception as exc:
        logger.error("pdf2image conversion failed: %s", exc)
        _EXTRACTION_CACHE[cache_key] = {}
        _PAGE_COUNT_CACHE[cache_key] = 0
        return {}

    _PAGE_COUNT_CACHE[cache_key] = len(images)
    accumulated: dict[str, list[dict]] = {}

    # ── Process each page ─────────────────────────────────────────────────────
    for page_idx, image in enumerate(images):
        page_num = page_idx + 1

        # PIL image → base64 PNG
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        page_data = _process_page(image_b64, page_num)
        if page_data is None:
            continue

        section  = page_data.get("section")           # already validated above
        raw_rows = page_data.get("rows") or []

        rows_added = 0
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue

            label = str(raw.get("label", "")).strip()
            if not label:
                continue
            # Secondary ALL-CAPS safety net
            if _is_total_row(label):
                continue

            exercice_n  = _to_float(raw.get("amount_n"))
            exercice_n1 = _to_float(raw.get("amount_n1"))

            # Skip rows with no numeric data at all
            if exercice_n is None and exercice_n1 is None:
                continue

            accumulated.setdefault(section, []).append({   # type: ignore[arg-type]
                "label":       label,
                "exercice_n":  exercice_n,
                "exercice_n1": exercice_n1,
            })
            rows_added += 1

        logger.debug("Page %d: section=%s extracted_rows=%d", page_num, section, rows_added)

    # ── Build final result ────────────────────────────────────────────────────
    result: dict[str, dict] = {}
    for section in ("bilan_actif", "bilan_passif", "compte_de_resultat"):
        rows = accumulated.get(section, [])
        if rows:
            result[section] = {
                "rows":       rows,
                "confidence": 1.0,
                "source":     "vision",
            }

    _EXTRACTION_CACHE[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# PDFResult — structured wrapper (interface unchanged)
# ---------------------------------------------------------------------------

@dataclass
class PDFResult:
    """
    Structured result of a plaquette PDF extraction.

    Attributes
    ----------
    sections : dict
        Raw output of ``extract_plaquette_data()``.
    page_count : int
        Number of pages in the source PDF.
    """

    sections:   dict[str, dict]
    page_count: int

    def rows(self, section: str) -> list[dict]:
        return self.sections.get(section, {}).get("rows", [])

    def confidence(self, section: str) -> float:
        return self.sections.get(section, {}).get("confidence", 0.0)

    def all_rows(self) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        for section_name, section_data in self.sections.items():
            for row in section_data.get("rows", []):
                out.append((section_name, row))
        return out

    @property
    def found_sections(self) -> list[str]:
        return list(self.sections.keys())


# ---------------------------------------------------------------------------
# PDFExtractor — public API (interface unchanged)
# ---------------------------------------------------------------------------

class PDFExtractor:
    """
    Extract financial tables from a French annual report (plaquette) PDF
    using Claude Vision API (claude-sonnet-4-6).

    Usage
    -----
    >>> result = PDFExtractor.from_bytes(raw_pdf_bytes)
    >>> print(result.found_sections)
    ['bilan_actif', 'bilan_passif', 'compte_de_resultat']
    >>> for row in result.rows("bilan_actif"):
    ...     print(row["label"], row["exercice_n"])
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def extract(self) -> PDFResult:
        return self._process(self.path.read_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes) -> PDFResult:
        return cls._process(raw)

    @staticmethod
    def _process(raw: bytes) -> PDFResult:
        sections  = extract_plaquette_data(raw)
        cache_key = hashlib.sha256(raw).hexdigest()
        page_count = _PAGE_COUNT_CACHE.get(cache_key, 0)
        return PDFResult(sections=sections, page_count=page_count)
