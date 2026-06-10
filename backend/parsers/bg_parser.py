"""
BGParser — Balance Générale Excel parser (S&W standard format).

Input format (Excel .xlsx):
    Date | Journal | Compte | Ref | Libellé | Solde debit | Solde credit | Devise

Account numbers are integers in the file (e.g. 101200, 411000) and are stored
as strings so that PCG prefix matching works directly:

    str(411000) = "411000"  →  startswith("411") = True

Net balance per account:
    net = (Solde debit  or 0) − (Solde credit or 0)

Positive net = debit balance (assets, expenses).
Negative net = credit balance (liabilities, revenues) — reconcile() calls abs().

Column matching is accent-insensitive and case-insensitive so minor header
variations in the source file are handled gracefully.

Public interface:
    BGParser.from_bytes(raw: bytes) → BGResult
    BGResult.to_balances_dict()     → dict[str, float]
    BGResult.errors                 → list[str]
    BGResult.row_count              → int
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Column-name helpers
# ---------------------------------------------------------------------------

def _norm_col(name: str) -> str:
    """Accent-strip + lower + collapse non-alphanumeric for fuzzy matching."""
    s = str(name).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[\s._\-]+", "", s)


def _find_col(cols: list[str], *candidates: str) -> Optional[str]:
    """Return the first col name that matches any candidate, or None."""
    normed = {_norm_col(c): c for c in cols}
    for cand in candidates:
        if (hit := normed.get(_norm_col(cand))) is not None:
            return hit
    return None


# ---------------------------------------------------------------------------
# Vectorized amount parser
# ---------------------------------------------------------------------------

def _parse_amount_series(s: pd.Series) -> pd.Series:
    """
    Parse a Series of amount strings (or numerics) to float64, vectorized.

    Empty cells and NaN → NaN (callers decide whether to fillna(0)).
    Handles French formatting: comma decimal, space/NBSP thousands, paren negatives.
    """
    str_s = s.astype(str).str.strip()
    was_nan = str_s.str.lower().isin(["nan", "none", ""])

    neg_paren = str_s.str.match(r"^\(.*\)$")
    str_s = str_s.str.replace(r"^\(|\)$", "", regex=True)
    str_s = str_s.str.replace(r"[\s\xa0 ]", "", regex=True)
    str_s = str_s.str.replace(",", ".", regex=False)
    str_s = str_s.str.replace(r"[^\d.\-]", "", regex=True)

    result = pd.to_numeric(str_s, errors="coerce")
    result = result.where(~neg_paren, -result)
    result = result.where(~was_nan, other=float("nan"))
    return result


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BGResult:
    """
    Parsed Balance Générale.

    ``balances`` maps str(Compte) → net_balance where:
        net_balance = Solde_debit − Solde_credit
    """

    balances:  dict[str, float]  # e.g. {"411000": 12345.67, "101200": -50000.0}
    errors:    list[str]
    row_count: int

    def to_balances_dict(self) -> dict[str, float]:
        """
        Return {compte_str: net_balance}.

        Same interface as FECResult.to_balances_dict() — consumed by reconcile().
        """
        return dict(self.balances)


# ---------------------------------------------------------------------------
# Core parsing logic
# ---------------------------------------------------------------------------

def _parse_bg_bytes(raw: bytes) -> BGResult:
    errors: list[str] = []

    # ── Load workbook ────────────────────────────────────────────────────────
    try:
        df = pd.read_excel(io.BytesIO(raw), dtype=str, engine="openpyxl", header=0)
    except Exception as exc:
        return BGResult(
            balances={},
            errors=[f"Lecture Excel impossible : {exc}"],
            row_count=0,
        )

    df.columns = [str(c).strip() for c in df.columns]
    cols = list(df.columns)

    # ── Locate required columns ──────────────────────────────────────────────
    compte_col = _find_col(
        cols, "Compte", "compte", "CompteNum", "N° compte", "numero_compte",
    )
    debit_col = _find_col(
        cols,
        "Solde debit", "Solde débit", "Soldedebit", "Soldedébit",
        "solde_debit", "SoldeDebit", "Debit", "Débit",
    )
    credit_col = _find_col(
        cols,
        "Solde credit", "Solde crédit", "Soldecredit", "Soldecrédit",
        "solde_credit", "SoldeCredit", "Credit", "Crédit",
    )

    missing = [
        name
        for name, col in [
            ("Compte",       compte_col),
            ("Solde debit",  debit_col),
            ("Solde credit", credit_col),
        ]
        if col is None
    ]
    if missing:
        return BGResult(
            balances={},
            errors=[
                f"Colonnes manquantes dans la Balance Générale : {', '.join(missing)}. "
                f"Colonnes trouvées : {', '.join(cols[:10])}"
            ],
            row_count=0,
        )

    # ── Normalise account numbers ────────────────────────────────────────────
    df["_compte"] = (
        df[compte_col]
        .fillna("")
        .astype(str)
        .str.strip()
        # Excel may encode integers as floats: "411000.0" → "411000"
        .str.replace(r"\.0+$", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
    )

    # Keep only rows with purely numeric account codes (skip totals / headers)
    valid_mask = df["_compte"].str.match(r"^\d{3,}")
    invalid_rows = (~valid_mask).sum()
    if invalid_rows > 0:
        errors.append(
            f"{invalid_rows} ligne(s) ignorée(s) (code compte non numérique)"
        )
    df = df[valid_mask].copy()

    if df.empty:
        return BGResult(
            balances={},
            errors=errors + ["Aucune ligne valide (code compte numérique ≥ 3 chiffres attendu)"],
            row_count=0,
        )

    # ── Parse amounts (vectorized) ───────────────────────────────────────────
    df["_debit"]  = _parse_amount_series(df[debit_col]).fillna(0.0)
    df["_credit"] = _parse_amount_series(df[credit_col]).fillna(0.0)

    # ── Net balance per account (groupby handles duplicate account rows) ──────
    df["_net"] = df["_debit"] - df["_credit"]
    net_series = df.groupby("_compte")["_net"].sum()

    balances: dict[str, float] = {k: float(v) for k, v in net_series.items()}

    return BGResult(
        balances=balances,
        errors=errors,
        row_count=len(df),
    )


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class BGParser:
    """
    Parse a Balance Générale Excel file (.xlsx, S&W standard).

    Format:
        Date | Journal | Compte | Ref | Libellé | Solde debit | Solde credit | Devise

    Column names are matched case-insensitively with accent normalisation.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def parse(self) -> BGResult:
        return _parse_bg_bytes(self.path.read_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes) -> BGResult:
        return _parse_bg_bytes(raw)
