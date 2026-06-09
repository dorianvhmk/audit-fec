"""
FECParser — supports Excel (.xlsx) and pipe-delimited TXT (.txt) FEC files.

Excel format (primary, detected from ZIP magic bytes PK\\x03\\x04):
    Columns: JournalCode, JournalLib, EcritureNum, date, CompteNum,
    CompteLib, CompAuxNum, CompAuxLib, PieceRef, PieceDate, EcritureLib,
    Partenaire, Montant, Sens, Montant.1, EcritureLet, DateLet, ValidDate,
    Montantdevise, Idevise, CompCode, Periode, Dev.I, Poste, Parten., Bque sté

    Balance logic:
        Sens == "D"  →  total_debit  += Montant
        Sens == "C"  →  total_credit += Montant
        solde = total_debit − total_credit

TXT format (fallback, DGFiP arrêté 29/07/2013):
    Pipe-delimited, 18+ columns, separate Debit / Credit columns.

Public interface (unchanged):
    FECParser(path).parse()        → FECResult
    FECParser.from_bytes(raw)      → FECResult
    FECResult.to_balances_dict()   → dict[str, float]
    FECResult.row_count            int
    FECResult.errors               list[str]
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Magic-byte detection
# ---------------------------------------------------------------------------

_XLSX_MAGIC = b"PK\x03\x04"  # all .xlsx/.xlsm files are ZIP archives


def _is_xlsx(raw: bytes) -> bool:
    return len(raw) >= 4 and raw[:4] == _XLSX_MAGIC


# ---------------------------------------------------------------------------
# Data model (public — consumed by services/reconciliation.py)
# ---------------------------------------------------------------------------

@dataclass
class FECLine:
    """Single journal entry line (populated for TXT; empty list for Excel)."""
    journal_code: str
    journal_lib: str
    ecriture_num: str
    ecriture_date: Optional[date]
    compte_num: str
    compte_lib: str
    comp_aux_num: str
    comp_aux_lib: str
    piece_ref: str
    piece_date: Optional[date]
    ecriture_lib: str
    debit: float
    credit: float
    ecriture_let: str
    date_let: Optional[date]
    valid_date: Optional[date]
    montant_devise: Optional[float]
    idevise: str


@dataclass
class AccountBalance:
    """Aggregated debit / credit totals for one CompteNum."""
    compte_num: str
    compte_lib: str
    total_debit: float = 0.0
    total_credit: float = 0.0

    @property
    def solde(self) -> float:
        """Net balance: total_debit − total_credit.
        Positive = solde débiteur; negative = solde créditeur."""
        return self.total_debit - self.total_credit

    @property
    def solde_debiteur(self) -> float:
        return max(self.solde, 0.0)

    @property
    def solde_crediteur(self) -> float:
        return max(-self.solde, 0.0)


@dataclass
class FECResult:
    """Parsed FEC: per-account balance aggregates + optional raw lines."""
    lines: list[FECLine]
    balances: dict[str, AccountBalance]   # keyed by CompteNum
    errors: list[str]
    encoding: str          # "xlsx" for Excel files
    delimiter: str         # "" for Excel files
    row_count: int

    def to_balances_dict(self) -> dict[str, float]:
        """Return {CompteNum: net_solde} — consumed by reconciliation.reconcile()."""
        return {num: bal.solde for num, bal in self.balances.items()}

    def balance(self, prefix: str) -> float:
        """Sum of net soldes for all accounts whose CompteNum starts with *prefix*."""
        return sum(
            bal.solde for num, bal in self.balances.items() if num.startswith(prefix)
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DATE_YYYYMMDD = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_DATE_ISO      = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DATE_DMY      = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_NEG_PAREN     = re.compile(r"^\(\s*(.+?)\s*\)$")
_THOUSANDS_SEP = re.compile(r"(?<=\d)[\s  ](?=\d)")


def _parse_date(raw: str) -> Optional[date]:
    s = raw.strip()
    if not s:
        return None
    for pat, order in ((_DATE_YYYYMMDD, "ymd"), (_DATE_ISO, "ymd"), (_DATE_DMY, "dmy")):
        m = pat.match(s)
        if m:
            g = m.groups()
            try:
                return (
                    date(int(g[0]), int(g[1]), int(g[2])) if order == "ymd"
                    else date(int(g[2]), int(g[1]), int(g[0]))
                )
            except ValueError:
                return None
    return None


def _parse_float(raw: str) -> float:
    """Parse a French or international number string to float. Returns 0.0 on failure."""
    s = str(raw).strip()
    if not s or s in {"-", "–", "—", "N/A"}:
        return 0.0
    negative = False
    m = _NEG_PAREN.match(s)
    if m:
        s, negative = m.group(1), True
    elif s.startswith("-"):
        s, negative = s[1:], True
    s = _THOUSANDS_SEP.sub("", s).replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") \
            else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Excel parsing
# ---------------------------------------------------------------------------

def _norm_col(name: str) -> str:
    """Normalise a column header: lower, strip accents + punctuation."""
    s = str(name).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")  # strip accents
    return re.sub(r"[\s._\-]+", "", s)


def _find_col(cols: list[str], *candidates: str) -> Optional[str]:
    """Return the first column whose normalised header matches any candidate."""
    normed = {_norm_col(c): c for c in cols}
    for cand in candidates:
        match = normed.get(_norm_col(cand))
        if match is not None:
            return match
    return None


def _safe_float(val) -> float:
    """Convert a pandas cell to float; return 0.0 on null / invalid."""
    try:
        if pd.isna(val):
            return 0.0
    except (TypeError, ValueError):
        pass
    return _parse_float(str(val))


def _parse_excel_bytes(raw: bytes) -> FECResult:
    errors: list[str] = []

    try:
        df = pd.read_excel(io.BytesIO(raw), dtype=str, engine="openpyxl", header=0)
    except Exception as exc:
        return FECResult(
            lines=[], balances={}, errors=[f"Lecture Excel impossible: {exc}"],
            encoding="xlsx", delimiter="", row_count=0,
        )

    df.columns = [str(c).strip() for c in df.columns]
    cols = list(df.columns)

    compte_num_col = _find_col(cols, "CompteNum", "compte_num", "comptenum", "Compte Num")
    montant_col    = _find_col(cols, "Montant", "montant")
    sens_col       = _find_col(cols, "Sens", "sens")
    compte_lib_col = _find_col(cols, "CompteLib", "compte_lib", "comptelib", "Compte Lib")

    missing = [
        name for name, col in [
            ("CompteNum", compte_num_col),
            ("Montant",   montant_col),
            ("Sens",      sens_col),
        ] if col is None
    ]
    if missing:
        return FECResult(
            lines=[], balances={},
            errors=[f"Colonnes manquantes dans le fichier Excel: {', '.join(missing)}"],
            encoding="xlsx", delimiter="", row_count=0,
        )

    balances: dict[str, AccountBalance] = {}
    skipped = 0

    for idx, row in df.iterrows():
        compte_num = str(row[compte_num_col]).strip()
        if not compte_num or compte_num.lower() in ("nan", "none", ""):
            skipped += 1
            continue

        montant = _safe_float(row[montant_col])
        sens_raw = row[sens_col] if pd.notna(row[sens_col]) else ""
        sens = str(sens_raw).strip().upper()

        compte_lib = ""
        if compte_lib_col is not None:
            v = row[compte_lib_col]
            if pd.notna(v) and str(v).lower() not in ("nan", "none"):
                compte_lib = str(v).strip()

        if compte_num not in balances:
            balances[compte_num] = AccountBalance(
                compte_num=compte_num,
                compte_lib=compte_lib,
            )

        if sens == "D":
            balances[compte_num].total_debit += montant
        elif sens == "C":
            balances[compte_num].total_credit += montant
        else:
            errors.append(
                f"Ligne {idx + 2}: Sens inconnu '{sens}' pour compte {compte_num} — ignoré"
            )

    total_rows = len(df) - skipped
    return FECResult(
        lines=[],
        balances=balances,
        errors=errors,
        encoding="xlsx",
        delimiter="",
        row_count=total_rows,
    )


# ---------------------------------------------------------------------------
# TXT parsing (DGFiP pipe-delimited, arrêté 29/07/2013)
# ---------------------------------------------------------------------------

_TXT_COLUMNS = [
    "JournalCode", "JournalLib", "EcritureNum", "EcritureDate",
    "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib",
    "PieceRef", "PieceDate", "EcritureLib",
    "Debit", "Credit",
    "EcritureLet", "DateLet", "ValidDate",
    "Montantdevise", "Idevise",
]


def _detect_encoding(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _detect_delimiter(first_line: str) -> str:
    counts = {"|": first_line.count("|"), "\t": first_line.count("\t"), ";": first_line.count(";")}
    best = max(counts, key=lambda c: counts[c])
    return best if counts[best] >= 3 else "|"


def _norm_header(raw: str) -> str:
    clean = raw.strip().lstrip("﻿")
    return next((col for col in _TXT_COLUMNS if col.lower() == clean.lower()), clean)


def _parse_float_opt(raw: str) -> Optional[float]:
    s = raw.strip()
    return None if not s else _parse_float(s)


def _parse_txt_bytes(raw: bytes) -> FECResult:
    encoding  = _detect_encoding(raw)
    text      = raw.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
    lines_raw = text.split("\n")
    delimiter = _detect_delimiter(lines_raw[0]) if lines_raw else "|"

    reader = csv.DictReader(
        io.StringIO(text), delimiter=delimiter, restkey="_extra", restval=""
    )
    if not reader.fieldnames:
        return FECResult(
            lines=[], balances={}, errors=["Fichier vide ou sans en-tête"],
            encoding=encoding, delimiter=delimiter, row_count=0,
        )

    col_map = {raw_col: _norm_header(raw_col) for raw_col in reader.fieldnames}

    lines:    list[FECLine]              = []
    balances: dict[str, AccountBalance] = {}
    errors:   list[str]                 = []

    for row_num, raw_row in enumerate(reader, start=2):
        row = {col_map.get(k, k): v for k, v in raw_row.items() if k != "_extra"}

        compte_num = row.get("CompteNum", "").strip()
        if not compte_num:
            errors.append(f"Ligne {row_num}: CompteNum vide — ignorée")
            continue

        try:
            debit  = _parse_float(row.get("Debit",  ""))
            credit = _parse_float(row.get("Credit", ""))

            lines.append(FECLine(
                journal_code   = row.get("JournalCode", "").strip(),
                journal_lib    = row.get("JournalLib",  "").strip(),
                ecriture_num   = row.get("EcritureNum", "").strip(),
                ecriture_date  = _parse_date(row.get("EcritureDate", "")),
                compte_num     = compte_num,
                compte_lib     = row.get("CompteLib",   "").strip(),
                comp_aux_num   = row.get("CompAuxNum",  "").strip(),
                comp_aux_lib   = row.get("CompAuxLib",  "").strip(),
                piece_ref      = row.get("PieceRef",    "").strip(),
                piece_date     = _parse_date(row.get("PieceDate", "")),
                ecriture_lib   = row.get("EcritureLib", "").strip(),
                debit          = debit,
                credit         = credit,
                ecriture_let   = row.get("EcritureLet", "").strip(),
                date_let       = _parse_date(row.get("DateLet",    "")),
                valid_date     = _parse_date(row.get("ValidDate",  "")),
                montant_devise = _parse_float_opt(row.get("Montantdevise", "")),
                idevise        = row.get("Idevise", "").strip(),
            ))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Ligne {row_num}: erreur inattendue — {exc}")
            continue

        if compte_num not in balances:
            balances[compte_num] = AccountBalance(
                compte_num=compte_num,
                compte_lib=row.get("CompteLib", "").strip(),
            )
        balances[compte_num].total_debit  += debit
        balances[compte_num].total_credit += credit

    return FECResult(
        lines=lines,
        balances=balances,
        errors=errors,
        encoding=encoding,
        delimiter=delimiter,
        row_count=len(lines),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _parse_bytes(raw: bytes) -> FECResult:
    """Auto-detect format from magic bytes — filename extension is irrelevant."""
    if _is_xlsx(raw):
        return _parse_excel_bytes(raw)
    return _parse_txt_bytes(raw)


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class FECParser:
    """
    Parse a FEC file from disk or raw bytes.

    Accepts both Excel (.xlsx) and pipe-delimited TXT (.txt) formats.
    Format is auto-detected from magic bytes; the filename extension is ignored.

    Examples
    --------
    >>> result = FECParser("export_fec.xlsx").parse()
    >>> print(result.row_count, "lignes —", len(result.errors), "erreurs")
    >>> print(result.balance("411"))   # net créances clients
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def parse(self) -> FECResult:
        """Read and parse the FEC file. Returns a :class:`FECResult`."""
        return _parse_bytes(self.path.read_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes) -> FECResult:
        """Parse from raw bytes (used when downloading from Supabase Storage)."""
        return _parse_bytes(raw)
