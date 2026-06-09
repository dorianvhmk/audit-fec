"""
Extract financial line items from a plaquette PDF using pdfplumber.

Strategy:
1. Extract all tables from every page.
2. Classify each table as bilan actif, bilan passif, or compte de résultat
   based on header keywords.
3. Parse rows into PlaquetteLine objects with label + montant (N and N-1 when present).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum

import pdfplumber


class TableType(str, Enum):
    BILAN_ACTIF = "bilan_actif"
    BILAN_PASSIF = "bilan_passif"
    COMPTE_RESULTAT = "compte_resultat"
    UNKNOWN = "unknown"


@dataclass
class PlaquetteLine:
    table_type: TableType
    label: str
    montant_n: Decimal | None       # exercice N (colonne la plus récente)
    montant_n1: Decimal | None      # exercice N-1 (si présent)
    raw_row: list[str] = field(default_factory=list, repr=False)


@dataclass
class PdfExtractResult:
    lines: list[PlaquetteLine]
    page_count: int
    errors: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NEGATIVE_RE = re.compile(r"^\((.+)\)$")   # (1 234) → -1234


def _clean_amount(raw: str) -> Decimal | None:
    if raw is None:
        return None
    s = str(raw).strip().replace("\xa0", "").replace(" ", "").replace(" ", "")
    if not s or s in ("-", "–", "—", ""):
        return None
    negative = False
    m = _NEGATIVE_RE.match(s)
    if m:
        s = m.group(1)
        negative = True
    s = s.replace(",", ".").replace(".", "", s.count(".") - 1) if s.count(".") > 1 else s.replace(",", ".")
    try:
        val = Decimal(s)
        return -val if negative else val
    except InvalidOperation:
        return None


_ACTIF_KEYWORDS = {"actif", "immobilisation", "créance", "trésorerie actif", "actifs"}
_PASSIF_KEYWORDS = {"passif", "capitaux propres", "dettes", "provision", "passifs"}
_RESULTAT_KEYWORDS = {"résultat", "produit", "charge", "chiffre d'affaires", "compte de résultat"}


def _classify_table(headers: list[str]) -> TableType:
    joined = " ".join(h.lower() for h in headers if h)
    if any(k in joined for k in _ACTIF_KEYWORDS):
        return TableType.BILAN_ACTIF
    if any(k in joined for k in _PASSIF_KEYWORDS):
        return TableType.BILAN_PASSIF
    if any(k in joined for k in _RESULTAT_KEYWORDS):
        return TableType.COMPTE_RESULTAT
    return TableType.UNKNOWN


def _looks_like_amount_col(header: str) -> bool:
    h = header.lower().strip()
    return bool(re.search(r"\d{4}|montant|net|brut|total|exercice", h))


def _find_amount_cols(headers: list[str]) -> tuple[int | None, int | None]:
    """Return column indices for N and N-1 amounts."""
    amount_indices = [i for i, h in enumerate(headers) if _looks_like_amount_col(str(h))]
    col_n = amount_indices[-1] if amount_indices else None
    col_n1 = amount_indices[-2] if len(amount_indices) >= 2 else None
    return col_n, col_n1


def _is_subtotal_or_empty(row: list[str]) -> bool:
    filled = [c for c in row if c and str(c).strip()]
    return len(filled) == 0


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract_plaquette(pdf_bytes: bytes) -> PdfExtractResult:
    lines: list[PlaquetteLine] = []
    errors: list[str] = []
    page_count = 0

    with pdfplumber.open(pdf_bytes if not isinstance(pdf_bytes, bytes) else __import__("io").BytesIO(pdf_bytes)) as pdf:
        page_count = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if not tables:
                continue

            for table in tables:
                if not table or len(table) < 2:
                    continue

                # First non-empty row is treated as header
                header_row = table[0]
                headers = [str(c).strip() if c else "" for c in header_row]

                table_type = _classify_table(headers)
                col_n, col_n1 = _find_amount_cols(headers)

                for row in table[1:]:
                    if _is_subtotal_or_empty(row):
                        continue

                    raw = [str(c).strip() if c else "" for c in row]

                    # Label: first non-empty cell
                    label = next((c for c in raw if c), "").strip()
                    if not label:
                        continue

                    montant_n = _clean_amount(raw[col_n]) if col_n is not None and col_n < len(raw) else None
                    montant_n1 = _clean_amount(raw[col_n1]) if col_n1 is not None and col_n1 < len(raw) else None

                    lines.append(PlaquetteLine(
                        table_type=table_type,
                        label=label,
                        montant_n=montant_n,
                        montant_n1=montant_n1,
                        raw_row=raw,
                    ))

    return PdfExtractResult(lines=lines, page_count=page_count, errors=errors)
