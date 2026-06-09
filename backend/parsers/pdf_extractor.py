"""
PDF financial table extractor for French annual reports (plaquettes sociales).

Extraction strategy
-------------------
1. Iterate pages with pdfplumber.
2. Detect section titles ("Bilan Actif", "Bilan Passif", "Compte de résultat")
   on each page by scanning text lines — this drives section assignment and is
   more reliable than scoring table content alone.
3. For each table on a page, assign it to the active section (title-based) or
   fall back to keyword-scoring when no title has been found yet.
4. Column selection uses a year-first strategy:
     • Find columns whose header contains a 4-digit year (31/12/YYYY) →
       first year col = exercice N, second year col = exercice N-1.
     • If no year headers, use the "3rd numeric column" rule (index 2 among
       non-label cols) → covers the 5-column Bilan and CR layout:
         Bilan: Rubriques | BRUT | AMORT | 31/12/N | 31/12/N-1
         CR:    Rubriques | France | Export | 31/12/N | 31/12/N-1
     • Fallback for simple 3-column tables: take last two cols as N / N-1.
5. ALL-CAPS label rows (section subtotals) are silently dropped.
6. Rows are accumulated per section across all pages.
7. If pdfplumber finds no structured tables at all, fall back to regex-based
   text extraction.

Returned structure
------------------
{
  "bilan_actif": {
      "rows": [{"label": str, "exercice_n": float|None, "exercice_n1": float|None}, ...],
      "confidence": float,
      "source": "table" | "text"
  },
  "bilan_passif":       { ... },
  "compte_de_resultat": { ... },
}
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pdfplumber

# ---------------------------------------------------------------------------
# In-process extraction cache (keyed by SHA-256 of the raw PDF bytes)
# Avoids re-parsing the same PDF within the same process lifetime, e.g.
# during development restarts or if analyze is triggered twice.
# ---------------------------------------------------------------------------

_EXTRACTION_CACHE: dict[str, dict] = {}  # sha256 hex → extracted tables dict

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

TableTypeStr = Literal["bilan_actif", "bilan_passif", "compte_de_resultat", "unknown"]
Row = dict  # {"label": str, "exercice_n": float|None, "exercice_n1": float|None}


@dataclass
class _TableCandidate:
    table_type: TableTypeStr
    confidence: float
    rows: list[Row]
    source: Literal["table", "text"]


# ---------------------------------------------------------------------------
# Title-line markers (primary section detection)
# ---------------------------------------------------------------------------

# Normalised (upper-case, accent-stripped) prefixes to look for in page text.
# A line is considered a section title if its normalised form STARTS WITH
# one of these markers (allowing "Bilan Actif AU 31/12/2023", etc.).
_TITLE_MARKERS: dict[str, list[str]] = {
    "bilan_actif":        ["BILAN ACTIF", "ACTIF DU BILAN"],
    "bilan_passif":       ["BILAN PASSIF", "PASSIF DU BILAN"],
    "compte_de_resultat": ["COMPTE DE RESULTAT"],
}

# Solo exact-match markers (only match when the ENTIRE line equals the token).
# Added to catch PDFs that simply write "ACTIF" / "PASSIF" as section headings.
_SOLO_MARKERS: dict[str, list[str]] = {
    "bilan_actif":  ["ACTIF"],
    "bilan_passif": ["PASSIF"],
}


# ---------------------------------------------------------------------------
# Keyword catalogues (fallback content-scoring)
# ---------------------------------------------------------------------------

_PRIMARY: dict[str, list[str]] = {
    "bilan_actif":        ["ACTIF"],
    "bilan_passif":       ["PASSIF"],
    "compte_de_resultat": ["PRODUITS", "CHARGES", "RESULTAT NET"],
}

_SECONDARY: dict[str, list[str]] = {
    "bilan_actif":        ["IMMOBILISATION", "STOCK", "CREANCE", "TRESORERIE", "DISPONIBILIT", "BRUT", "AMORT"],
    "bilan_passif":       ["CAPITAL", "RESERVE", "DETTE", "PROVISION", "EMPRUNT", "CAPITAUX PROPRES", "REPORT"],
    "compte_de_resultat": ["CHIFFRE", "VENTE", "ACHAT", "SALAIRE", "DOTATION", "PRODUIT", "CHARGE", "EXPLOITATION", "FINANCIER"],
}


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Upper-case, strip accents, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_only).strip().upper()


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------

_NEG_PAREN     = re.compile(r"^\(\s*(.+?)\s*\)$")
_CLEAN_THOUSANDS = re.compile(r"(?<=\d)[\s ](?=\d)")


def _parse_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"-", "–", "—", "N/A", ""}:
        return None

    negative = False
    m = _NEG_PAREN.match(s)
    if m:
        s, negative = m.group(1), True
    elif s.startswith("-"):
        s, negative = s[1:], True

    s = _CLEAN_THOUSANDS.sub("", s).replace(",", ".").replace(" ", "")
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Section detection helpers
# ---------------------------------------------------------------------------

def _detect_title_section(page_text: str) -> TableTypeStr | None:
    """
    Scan page text for a section-title line.

    Returns the matching section type on the first match, or None.
    """
    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        normed = _normalise(stripped)

        # Primary: starts-with match (allows date suffix, e.g. "BILAN ACTIF AU 31/12/2023")
        for ttype, markers in _TITLE_MARKERS.items():
            for marker in markers:
                if normed.startswith(marker):
                    return ttype  # type: ignore[return-value]

        # Solo: exact match only (avoids "ACTIF CIRCULANT" false-positive)
        for ttype, markers in _SOLO_MARKERS.items():
            if normed in markers:
                return ttype  # type: ignore[return-value]

    return None


def _score_table(cells_text: str) -> tuple[TableTypeStr, float]:
    """
    Keyword-scoring fallback.  Returns (type, confidence).
    Confidence < 0.15 → "unknown".
    """
    normed = _normalise(cells_text)
    scores: dict[str, float] = {}
    for ttype in ("bilan_actif", "bilan_passif", "compte_de_resultat"):
        primary_hit = any(kw in normed for kw in _PRIMARY[ttype])
        sec_kws = _SECONDARY[ttype]
        sec_hits = sum(1 for kw in sec_kws if kw in normed)
        scores[ttype] = 0.5 * (1.0 if primary_hit else 0.0) + 0.5 * sec_hits / len(sec_kws)

    best_type = max(scores, key=lambda t: scores[t])
    best_score = scores[best_type]
    if best_score < 0.15:
        return "unknown", best_score
    return best_type, round(best_score, 3)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# ALL-CAPS row filter
# ---------------------------------------------------------------------------

def _is_total_row(label: str) -> bool:
    """
    Return True for rows whose label is ALL CAPS — these are typically
    section subtotals / grand totals that must not be reconciled.

    Examples that are filtered: "TOTAL ACTIF IMMOBILISE", "CAPITAUX PROPRES",
    "TOTAL BILAN", "RESULTAT DE L EXERCICE".
    """
    alpha = [c for c in label if c.isalpha()]
    if len(alpha) < 3:
        return False
    return all(c.isupper() for c in alpha)


# ---------------------------------------------------------------------------
# Column detection — "3rd numeric column" strategy
# ---------------------------------------------------------------------------

def _find_net_amount_cols(
    headers: list[str],
) -> tuple[int | None, int | None]:
    """
    Return (col_n_index, col_n1_index).

    Priority
    --------
    1. Year headers: columns whose header matches ``\\d{4}`` →
       first year col = N, second = N-1.
    2. "3rd numeric column" rule: non-label cols index 2 and 3 (0-based)
       → covers 5-column Bilan/CR layout where cols 1–2 are BRUT/AMORT
       or France/Exportation and cols 3–4 are the net year values.
    3. Fallback for simple 2-col tables: take last two non-label cols.
    """
    n_headers = len(headers)
    if n_headers < 2:
        return None, None

    non_label = list(range(1, n_headers))

    # Strategy 1 — year-based headers (most reliable)
    year_cols = [
        i for i in non_label
        if re.search(r"\d{4}", _normalise(str(headers[i])))
    ]
    if year_cols:
        col_n  = year_cols[0]
        col_n1 = year_cols[1] if len(year_cols) >= 2 else None
        return col_n, col_n1

    # Strategy 2 — "3rd numeric column" (index 2 among non-label cols)
    if len(non_label) >= 3:
        col_n  = non_label[2]
        col_n1 = non_label[3] if len(non_label) >= 4 else None
        return col_n, col_n1

    # Strategy 3 — fallback for simple 2- or 1-column tables
    if len(non_label) >= 2:
        return non_label[0], non_label[1]
    if non_label:
        return non_label[0], None
    return None, None


# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------

def _forward_fill_label_col(rows: list[list[str | None]]) -> list[list[str | None]]:
    """Forward-fill the first column to handle vertically merged cells."""
    last: str | None = None
    out = []
    for row in rows:
        filled = list(row)
        if filled[0]:
            last = filled[0]
        elif last:
            filled[0] = last
        out.append(filled)
    return out


def _parse_table_rows(
    table: list[list[str | None]],
    table_type: TableTypeStr,  # kept for API compatibility, not used in logic
) -> list[Row]:
    """
    Convert a raw pdfplumber table into Row dicts.

    ALL-CAPS label rows (section subtotals / grand totals) are silently dropped.
    Rows with a label but no parseable numeric amounts are also dropped so that
    only genuine data lines reach the reconciler.
    """
    if not table or len(table) < 2:
        return []

    header_row = table[0]
    headers = [str(c).strip() if c else "" for c in header_row]
    col_n, col_n1 = _find_net_amount_cols(headers)

    data_rows = _forward_fill_label_col(table[1:])
    rows: list[Row] = []

    for raw in data_rows:
        cells = [str(c).strip() if c else "" for c in raw]

        if not any(cells):
            continue

        label = next((c for c in cells if c), "").strip()
        if not label:
            continue

        # Drop ALL-CAPS subtotal / total rows
        if _is_total_row(label):
            continue

        n  = _parse_amount(cells[col_n])  if col_n  is not None and col_n  < len(cells) else None
        n1 = _parse_amount(cells[col_n1]) if col_n1 is not None and col_n1 < len(cells) else None

        # Drop rows that carry no numeric data (pure header/section text rows)
        if n is None and n1 is None:
            continue

        rows.append({"label": label, "exercice_n": n, "exercice_n1": n1})

    return rows


# ---------------------------------------------------------------------------
# Text-based fallback
# ---------------------------------------------------------------------------

_FR_AMT_PAT = r"-?\s*\d[\d\s ]*(?:[,.]\d{1,2})?"

_TEXT_ROW_RE = re.compile(
    r"^(?P<label>.{4,?}?)"
    r"[ \t]{2,}"
    r"(?P<n1>" + _FR_AMT_PAT + r")"
    r"(?:[ \t]+(?P<n2>" + _FR_AMT_PAT + r"))?"
    r"\s*$",
    re.UNICODE,
)

_TEXT_SECTION_MARKERS: dict[str, list[str]] = {
    "bilan_actif":        ["BILAN ACTIF", "ACTIF"],
    "bilan_passif":       ["BILAN PASSIF", "PASSIF"],
    "compte_de_resultat": ["COMPTE DE RESULTAT", "PRODUITS D EXPLOITATION"],
}


def _detect_text_section(normed_line: str) -> TableTypeStr | None:
    for ttype, markers in _TEXT_SECTION_MARKERS.items():
        if any(normed_line.startswith(m) for m in markers):
            return ttype  # type: ignore[return-value]
    return None


def _extract_via_text(pdf: pdfplumber.PDF) -> list[_TableCandidate]:
    """Fallback: parse raw text line by line when no structured tables are found."""
    candidates: dict[str, _TableCandidate] = {}
    keyword_hits: dict[str, int] = {k: 0 for k in _PRIMARY}

    for page in pdf.pages:
        text = page.extract_text() or ""
        current_type: TableTypeStr | None = None

        for raw_line in text.splitlines():
            normed = _normalise(raw_line)
            if not normed:
                continue

            detected = _detect_text_section(normed)
            if detected:
                current_type = detected
                keyword_hits[current_type] += 1
                continue

            if current_type is None:
                continue

            m = _TEXT_ROW_RE.match(raw_line.strip())
            if not m:
                continue

            label = m.group("label").strip()
            if not label or _is_total_row(label):
                continue

            n_raw  = m.group("n2") or m.group("n1")
            n1_raw = m.group("n1") if m.group("n2") else None
            n  = _parse_amount(n_raw)
            n1 = _parse_amount(n1_raw)

            if n is None and n1 is None:
                continue

            if current_type not in candidates:
                candidates[current_type] = _TableCandidate(
                    table_type=current_type, confidence=0.0, rows=[], source="text"
                )
            candidates[current_type].rows.append(
                {"label": label, "exercice_n": n, "exercice_n1": n1}
            )

    for ttype in list(candidates):
        total = len(_PRIMARY[ttype]) + len(_SECONDARY[ttype])
        candidates[ttype].confidence = round(
            min(0.6, keyword_hits.get(ttype, 0) / max(total, 1)), 3
        )

    return list(candidates.values())


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_plaquette_data(pdf_bytes: bytes) -> dict[str, dict]:
    """
    Parse a plaquette PDF and return financial tables.

    Results are cached in-process by SHA-256 of the raw bytes — repeated
    calls with the same PDF (e.g. dev restarts, duplicate triggers) skip
    the full pdfplumber extraction.

    Returns
    -------
    dict with keys "bilan_actif", "bilan_passif", "compte_de_resultat"
    (absent if not found).  Each value::

        {
            "rows":       [{"label": str, "exercice_n": float|None, "exercice_n1": float|None}, ...],
            "confidence": float,
            "source":     "table" | "text",
        }
    """
    cache_key = hashlib.sha256(pdf_bytes).hexdigest()
    if cache_key in _EXTRACTION_CACHE:
        return _EXTRACTION_CACHE[cache_key]
    accumulated: dict[str, list[Row]] = {}
    best_confidence: dict[str, float] = {}
    best_source: dict[str, str] = {}
    any_tables_found = False

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        # Track the current section as we walk through pages.
        # Title detection drives the assignment; when no title is visible on a
        # page we carry the last known section forward (handles multi-page tables).
        current_section: TableTypeStr | None = None

        for page in pdf.pages:
            page_text = page.extract_text() or ""

            # Attempt title-based section detection on this page
            title_section = _detect_title_section(page_text)
            if title_section:
                current_section = title_section

            tables = page.extract_tables()
            if not tables:
                continue
            any_tables_found = True

            for raw_table in tables:
                if not raw_table or len(raw_table) < 2:
                    continue

                # Determine section type
                if current_section:
                    ttype: TableTypeStr = current_section
                    confidence = 0.85  # title-based detection is high-confidence
                else:
                    cells_text = " ".join(
                        str(cell) for row in raw_table for cell in row if cell
                    )
                    ttype, confidence = _score_table(cells_text)
                    if ttype == "unknown":
                        continue

                rows = _parse_table_rows(raw_table, ttype)
                if not rows:
                    continue

                # Accumulate rows; track the highest confidence seen for this section
                if ttype not in accumulated:
                    accumulated[ttype] = []
                    best_confidence[ttype] = confidence
                    best_source[ttype] = "table"
                else:
                    if confidence > best_confidence[ttype]:
                        best_confidence[ttype] = confidence

                accumulated[ttype].extend(rows)

        # If no structured tables, use text fallback
        if not any_tables_found:
            for tc in _extract_via_text(pdf):
                ttype_str = tc.table_type
                if ttype_str not in accumulated or tc.confidence > best_confidence.get(ttype_str, 0):
                    accumulated[ttype_str] = tc.rows
                    best_confidence[ttype_str] = tc.confidence
                    best_source[ttype_str] = "text"

    result: dict[str, dict] = {}
    for section in ("bilan_actif", "bilan_passif", "compte_de_resultat"):
        if section in accumulated and accumulated[section]:
            result[section] = {
                "rows":       accumulated[section],
                "confidence": best_confidence.get(section, 0.0),
                "source":     best_source.get(section, "table"),
            }

    _EXTRACTION_CACHE[cache_key] = result  # store in process-level cache
    return result


# ---------------------------------------------------------------------------
# PDFResult — structured wrapper
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dataclass


@_dataclass
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

    sections: dict[str, dict]
    page_count: int

    def rows(self, section: str) -> list[dict]:
        return self.sections.get(section, {}).get("rows", [])

    def confidence(self, section: str) -> float:
        return self.sections.get(section, {}).get("confidence", 0.0)

    def all_rows(self) -> list[tuple[str, dict]]:
        out = []
        for section_name, section_data in self.sections.items():
            for row in section_data.get("rows", []):
                out.append((section_name, row))
        return out

    @property
    def found_sections(self) -> list[str]:
        return list(self.sections.keys())


# ---------------------------------------------------------------------------
# PDFExtractor — public API
# ---------------------------------------------------------------------------

class PDFExtractor:
    """
    Extract financial tables from a French annual report (plaquette) PDF.

    Examples
    --------
    >>> result = PDFExtractor("plaquette.pdf").extract()
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
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            page_count = len(pdf.pages)
        sections = extract_plaquette_data(raw)
        return PDFResult(sections=sections, page_count=page_count)
