"""
PDF financial table extractor for French annual reports (plaquettes sociales).

Extraction strategy
-------------------
1. Iterate pages with pdfplumber.
2. For each page try table extraction first (pdfplumber's lattice/stream detector).
3. Classify every table as bilan_actif | bilan_passif | compte_de_resultat | unknown
   by scanning all cells for keyword signals.
4. Assign a confidence score (0–1) per table based on keyword hit-rate.
5. When a page yields no tables, fall back to raw text + regex line parsing.
6. Aggregate all classified rows into a result dict keyed by table type.

Returned structure
------------------
{
  "bilan_actif": {
      "rows": [{"label": str, "exercice_n": float|None, "exercice_n1": float|None}, ...],
      "confidence": float,   # 0.0 – 1.0, best confidence seen across pages
      "source": "table"|"text"
  },
  "bilan_passif":      { ... },
  "compte_de_resultat": { ... },
}

Missing sections are absent from the dict (not present as empty lists).
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

import pdfplumber

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
# Keyword catalogues
# ---------------------------------------------------------------------------

# These are upper-cased ASCII-normalised strings (accents stripped).
# Evaluated against the full concatenated text of each table.

_PRIMARY: dict[TableTypeStr, list[str]] = {
    "bilan_actif": ["ACTIF"],
    "bilan_passif": ["PASSIF"],
    "compte_de_resultat": ["PRODUITS", "CHARGES", "RESULTAT NET"],
}

_SECONDARY: dict[TableTypeStr, list[str]] = {
    "bilan_actif": [
        "IMMOBILISATION", "STOCK", "CREANCE", "TRESORERIE",
        "DISPONIBILIT", "BRUT", "AMORT",
    ],
    "bilan_passif": [
        "CAPITAL", "RESERVE", "DETTE", "PROVISION",
        "EMPRUNT", "CAPITAUX PROPRES", "REPORT",
    ],
    "compte_de_resultat": [
        "CHIFFRE", "VENTE", "ACHAT", "SALAIRE", "DOTATION",
        "PRODUIT", "CHARGE", "EXPLOITATION", "FINANCIER",
    ],
}

# Columns that indicate a GROSS value in a bilan actif — we skip them and
# use only NET columns for reconciliation.
_GROSS_COL_SIGNALS = {"BRUT", "AMORT", "DEPREC", "PROV"}

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

# French accounting uses spaces or non-breaking spaces as thousands separators,
# and commas as decimal separator. Negative amounts may appear as (1 234) or -1 234.
_NEG_PAREN = re.compile(r"^\(\s*(.+?)\s*\)$")
_CLEAN_THOUSANDS = re.compile(r"(?<=\d)[\s  ](?=\d)")

# Standalone amount: matches "1 234 567", "1 234 567,89", "(1 234)", "-1 234"
_AMOUNT_RE = re.compile(
    r"^\s*"
    r"(-|\()?"
    r"([\d][\d\s  ]*(?:[,.][\d]{1,2})?)"
    r"\)?"
    r"\s*$"
)


def _parse_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"-", "–", "—", "N/A", ""}:
        return None

    negative = False
    m = _NEG_PAREN.match(s)
    if m:
        s = m.group(1)
        negative = True
    elif s.startswith("-"):
        s = s[1:]
        negative = True

    # Remove thousands separators (spaces / NBSP)
    s = _CLEAN_THOUSANDS.sub("", s)
    # Normalise decimal
    s = s.replace(",", ".")
    # Remove any remaining whitespace
    s = s.replace(" ", "")

    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Table classification
# ---------------------------------------------------------------------------


def _score_table(cells_text: str) -> tuple[TableTypeStr, float]:
    """
    Return (table_type, confidence) for a table whose full concatenated
    cell text is `cells_text`.

    Confidence is computed per candidate type:
        primary_score   = 1.0 if any primary keyword found, else 0.0
        secondary_score = (secondary hits) / len(secondary keywords)
        confidence      = 0.5 * primary_score + 0.5 * secondary_score

    The type with the highest confidence wins; ties broken by primary.
    If no type scores above 0.15 the table is classified as "unknown".
    """
    normed = _normalise(cells_text)

    scores: dict[TableTypeStr, float] = {}
    for ttype in ("bilan_actif", "bilan_passif", "compte_de_resultat"):
        # Primary hit
        primary_hit = any(kw in normed for kw in _PRIMARY[ttype])  # type: ignore[arg-type]
        primary_score = 1.0 if primary_hit else 0.0

        # Secondary hits
        sec_kws = _SECONDARY[ttype]  # type: ignore[index]
        sec_hits = sum(1 for kw in sec_kws if kw in normed)
        secondary_score = sec_hits / len(sec_kws) if sec_kws else 0.0

        scores[ttype] = 0.5 * primary_score + 0.5 * secondary_score  # type: ignore[index]

    best_type = max(scores, key=lambda t: scores[t])
    best_score = scores[best_type]

    if best_score < 0.15:
        return "unknown", best_score
    return best_type, round(best_score, 3)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Column analysis helpers
# ---------------------------------------------------------------------------


def _is_amount_col_header(header: str) -> bool:
    h = _normalise(header)
    return bool(re.search(r"\d{4}|MONTANT|NET|BRUT|TOTAL|EXERCICE|PRECEDENT|N-1", h))


def _is_gross_col(header: str) -> bool:
    h = _normalise(header)
    return any(sig in h for sig in _GROSS_COL_SIGNALS)


def _find_net_amount_cols(
    headers: list[str],
    table_type: TableTypeStr,
) -> tuple[int | None, int | None]:
    """
    Return (col_n_index, col_n1_index) — indices of the N and N-1 amount
    columns in a row.

    For bilan_actif the NET columns come after the BRUT/AMORT columns.
    Strategy: collect all amount-looking column indices, then:
    - Drop any that look like BRUT/AMORT for bilan_actif.
    - col_n  = last remaining index
    - col_n1 = second-to-last remaining index
    """
    all_amount_idx = [
        i for i, h in enumerate(headers) if _is_amount_col_header(str(h))
    ]

    if table_type == "bilan_actif":
        # Filter out gross / amortissement columns
        net_idx = [i for i in all_amount_idx if not _is_gross_col(str(headers[i]))]
        candidate = net_idx if net_idx else all_amount_idx
    else:
        candidate = all_amount_idx

    if not candidate:
        # No column header gave us a hint — guess: last two non-label columns
        col_count = len(headers)
        candidate = list(range(max(0, col_count - 3), col_count))

    col_n = candidate[-1] if candidate else None
    col_n1 = candidate[-2] if len(candidate) >= 2 else None
    return col_n, col_n1


# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------


def _is_purely_header_row(raw: list[str | None]) -> bool:
    """True when a row has only text and no numeric-looking cells."""
    for cell in raw:
        if cell and _parse_amount(str(cell)) is not None:
            return False
    return True


def _forward_fill_label_col(rows: list[list[str | None]]) -> list[list[str | None]]:
    """
    pdfplumber emits None for cells that are part of a vertical merge.
    Forward-fill the first (label) column so every data row has a label.
    """
    last_label: str | None = None
    out = []
    for row in rows:
        filled = list(row)
        if filled[0]:
            last_label = filled[0]
        elif last_label:
            filled[0] = last_label
        out.append(filled)
    return out


def _parse_table_rows(
    table: list[list[str | None]],
    table_type: TableTypeStr,
) -> list[Row]:
    """
    Convert a raw pdfplumber table into a list of Row dicts.

    Rules:
    - Skip fully-empty rows.
    - Rows with a label but no parseable amounts are kept as section headers
      (exercice_n = exercice_n1 = None) — they are visible to the caller but
      will be skipped by the reconciler since plaquette_amount is None.
    - Forward-fill the label column to handle vertical cell merges.
    """
    if not table or len(table) < 2:
        return []

    header_row = table[0]
    headers = [str(c).strip() if c else "" for c in header_row]
    col_n, col_n1 = _find_net_amount_cols(headers, table_type)

    data_rows = _forward_fill_label_col(table[1:])
    rows: list[Row] = []

    for raw in data_rows:
        cells = [str(c).strip() if c else "" for c in raw]

        # Skip fully empty
        if not any(cells):
            continue

        # Label: first non-empty cell
        label = next((c for c in cells if c), "").strip()
        if not label:
            continue

        n = _parse_amount(cells[col_n]) if col_n is not None and col_n < len(cells) else None
        n1 = _parse_amount(cells[col_n1]) if col_n1 is not None and col_n1 < len(cells) else None

        rows.append({"label": label, "exercice_n": n, "exercice_n1": n1})

    return rows


# ---------------------------------------------------------------------------
# Text-based fallback (for PDFs without proper table structure)
# ---------------------------------------------------------------------------

# Pattern for a French financial amount: optional negative sign, digits with
# optional space-thousands-separator, optional comma-decimal.
_FR_AMT_PAT = r"-?\s*\d[\d  ]*(?:[,.]\d{1,2})?"

# A table row in text: label (≥4 chars), then 2+ spaces, then 1 or 2 amounts.
_TEXT_ROW_RE = re.compile(
    r"^(?P<label>.{4,?}?)"            # label (lazy)
    r"[ \t]{2,}"                       # separator
    r"(?P<n1>" + _FR_AMT_PAT + r")"   # first amount
    r"(?:"
    r"[ \t]+"
    r"(?P<n2>" + _FR_AMT_PAT + r")"   # optional second amount
    r")?"
    r"\s*$",
    re.UNICODE,
)

# Keywords that mark the start of each section in raw text
_SECTION_MARKERS: dict[TableTypeStr, list[str]] = {
    "bilan_actif": ["ACTIF", "BILAN ACTIF"],
    "bilan_passif": ["PASSIF", "BILAN PASSIF"],
    "compte_de_resultat": ["COMPTE DE RESULTAT", "PRODUITS D EXPLOITATION", "CHARGES D EXPLOITATION"],
}


def _detect_text_section(normed_line: str) -> TableTypeStr | None:
    for ttype, markers in _SECTION_MARKERS.items():
        if any(m in normed_line for m in markers):
            return ttype  # type: ignore[return-value]
    return None


def _extract_via_text(pdf: pdfplumber.PDF) -> list[_TableCandidate]:
    """
    Fallback: extract text line by line, detect section boundaries,
    parse amount rows with regex.
    """
    candidates: dict[TableTypeStr, _TableCandidate] = {}

    for page in pdf.pages:
        text = page.extract_text() or ""
        current_type: TableTypeStr | None = None
        keyword_hits: dict[TableTypeStr, int] = {
            "bilan_actif": 0,
            "bilan_passif": 0,
            "compte_de_resultat": 0,
        }

        for raw_line in text.splitlines():
            normed = _normalise(raw_line)
            if not normed:
                continue

            # Try to detect a section change
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
            n_raw = m.group("n2") or m.group("n1")   # prefer rightmost as N
            n1_raw = m.group("n1") if m.group("n2") else None

            n = _parse_amount(n_raw)
            n1 = _parse_amount(n1_raw)

            if label:
                if current_type not in candidates:
                    candidates[current_type] = _TableCandidate(
                        table_type=current_type,
                        confidence=0.0,
                        rows=[],
                        source="text",
                    )
                candidates[current_type].rows.append(
                    {"label": label, "exercice_n": n, "exercice_n1": n1}
                )

        # Compute confidence from keyword hit density
        for ttype in list(candidates):
            total_expected = len(_PRIMARY[ttype]) + len(_SECONDARY[ttype])
            hits = keyword_hits.get(ttype, 0)
            # Text fallback gets a maximum confidence of 0.6 (less reliable than table)
            candidates[ttype].confidence = round(
                min(0.6, hits / max(total_expected, 1)), 3
            )

    return list(candidates.values())


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------


def extract_plaquette_data(pdf_bytes: bytes) -> dict[str, dict]:
    """
    Parse a plaquette PDF and return financial tables.

    Parameters
    ----------
    pdf_bytes : bytes
        Raw PDF file content.

    Returns
    -------
    dict with keys "bilan_actif", "bilan_passif", "compte_de_resultat"
    (absent if the section was not found).  Each value is::

        {
            "rows":       [{"label": str, "exercice_n": float|None, "exercice_n1": float|None}, ...],
            "confidence": float,   # 0.0 – 1.0
            "source":     "table" | "text",
        }
    """
    # Accumulate candidates across pages; for each table type we keep the
    # one with the highest confidence.
    best: dict[TableTypeStr, _TableCandidate] = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        any_tables_found = False

        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if not tables:
                continue
            any_tables_found = True

            for raw_table in tables:
                if not raw_table or len(raw_table) < 2:
                    continue

                # Build full cell text for classification
                cells_text = " ".join(
                    str(cell) for row in raw_table for cell in row if cell
                )
                ttype, confidence = _score_table(cells_text)
                if ttype == "unknown":
                    continue

                rows = _parse_table_rows(raw_table, ttype)
                if not rows:
                    continue

                cand = _TableCandidate(
                    table_type=ttype,
                    confidence=confidence,
                    rows=rows,
                    source="table",
                )

                # Keep only the highest-confidence candidate per type,
                # but merge rows if the same type spans multiple pages.
                if ttype not in best:
                    best[ttype] = cand
                else:
                    existing = best[ttype]
                    if confidence > existing.confidence:
                        # Higher-confidence table replaces metadata but we
                        # still append rows (same section spread over pages).
                        best[ttype] = _TableCandidate(
                            table_type=ttype,
                            confidence=confidence,
                            rows=existing.rows + rows,
                            source="table",
                        )
                    else:
                        existing.rows.extend(rows)

        # If pdfplumber found no structured tables, fall back to text extraction
        if not any_tables_found:
            text_candidates = _extract_via_text(pdf)
            for tc in text_candidates:
                if tc.table_type not in best or tc.confidence > best[tc.table_type].confidence:
                    best[tc.table_type] = tc  # type: ignore[index]

    # Serialise to plain dicts for JSON-friendliness
    result: dict[str, dict] = {}
    valid_types: list[TableTypeStr] = ["bilan_actif", "bilan_passif", "compte_de_resultat"]
    for ttype in valid_types:
        if ttype in best:
            c = best[ttype]
            result[ttype] = {
                "rows": c.rows,
                "confidence": c.confidence,
                "source": c.source,
            }

    return result


# ---------------------------------------------------------------------------
# PDFResult — structured wrapper around the raw dict
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dataclass
from pathlib import Path as _Path


@_dataclass
class PDFResult:
    """
    Structured result of a plaquette PDF extraction.

    Attributes
    ----------
    sections : dict
        Raw output of ``extract_plaquette_data()``.
        Keys: "bilan_actif", "bilan_passif", "compte_de_resultat".
        Each value: ``{"rows": [...], "confidence": float, "source": str}``.
    page_count : int
        Number of pages in the source PDF.
    """

    sections: dict[str, dict]
    page_count: int

    def rows(self, section: str) -> list[dict]:
        """Return the list of parsed rows for *section*, or [] if not found."""
        return self.sections.get(section, {}).get("rows", [])

    def confidence(self, section: str) -> float:
        """Extraction confidence for *section* (0–1), or 0.0 if not found."""
        return self.sections.get(section, {}).get("confidence", 0.0)

    def all_rows(self) -> list[tuple[str, dict]]:
        """Yield (section_name, row_dict) for every row across all sections."""
        out = []
        for section_name, section_data in self.sections.items():
            for row in section_data.get("rows", []):
                out.append((section_name, row))
        return out

    @property
    def found_sections(self) -> list[str]:
        return list(self.sections.keys())


# ---------------------------------------------------------------------------
# PDFExtractor — file-path-based public class
# ---------------------------------------------------------------------------

class PDFExtractor:
    """
    Extract financial tables from a French annual report PDF.

    Parameters
    ----------
    path : str | Path
        Path to the plaquette PDF file.

    Examples
    --------
    >>> result = PDFExtractor("plaquette.pdf").extract()
    >>> print(result.found_sections)
    ['bilan_actif', 'bilan_passif', 'compte_de_resultat']
    >>> print(result.confidence("bilan_actif"))
    0.857
    >>> for row in result.rows("compte_de_resultat"):
    ...     print(row["label"], row["exercice_n"])
    """

    def __init__(self, path: str | _Path) -> None:
        self.path = _Path(path)

    def extract(self) -> PDFResult:
        """Read the PDF and extract all financial sections.  Returns a :class:`PDFResult`."""
        raw = self.path.read_bytes()
        return self._from_bytes(raw)

    @classmethod
    def from_bytes(cls, raw: bytes) -> PDFResult:
        """Extract from raw bytes (useful when reading from Supabase Storage)."""
        return cls._from_bytes_static(raw)

    @staticmethod
    def _from_bytes_static(raw: bytes) -> PDFResult:
        # Count pages separately so PDFResult carries it
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            page_count = len(pdf.pages)
        sections = extract_plaquette_data(raw)
        return PDFResult(sections=sections, page_count=page_count)

    def _from_bytes(self, raw: bytes) -> PDFResult:
        return PDFExtractor._from_bytes_static(raw)
