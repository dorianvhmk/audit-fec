"""
FECParser — DGFiP Fichier des Écritures Comptables (arrêté 29/07/2013).

Usage
-----
    from parsers.fec_parser import FECParser

    result = FECParser("export_fec.txt").parse()
    print(result.row_count, "écritures —", len(result.errors), "erreurs")

    for compte_num, bal in sorted(result.balances.items()):
        print(f"{compte_num}  {bal.compte_lib:40}  solde={bal.solde:>15,.2f}")

File format
-----------
Pipe-delimited text, one header row + N data rows.
18 mandatory columns (some optional at end):

  1  JournalCode     2  JournalLib      3  EcritureNum
  4  EcritureDate    5  CompteNum       6  CompteLib
  7  CompAuxNum      8  CompAuxLib      9  PieceRef
 10  PieceDate      11  EcritureLib    12  Debit
 13  Credit         14  EcritureLet    15  DateLet
 16  ValidDate      17  Montantdevise  18  Idevise

Encodings handled : UTF-8-sig (BOM), UTF-8, ISO-8859-1 (Latin-1).
Delimiters handled: pipe |, tab \\t, semicolon ;.
Amount format     : "1 234 567,89" or "1234567.89" or "(1 234 567)".
Date format       : YYYYMMDD  (some exporters use YYYY-MM-DD or DD/MM/YYYY).
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Column names (canonical, case-insensitive match during parsing)
# ---------------------------------------------------------------------------

_COLUMNS = [
    "JournalCode", "JournalLib", "EcritureNum", "EcritureDate",
    "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib",
    "PieceRef", "PieceDate", "EcritureLib",
    "Debit", "Credit",
    "EcritureLet", "DateLet", "ValidDate",
    "Montantdevise", "Idevise",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FECLine:
    journal_code: str
    journal_lib: str
    ecriture_num: str
    ecriture_date: date | None
    compte_num: str
    compte_lib: str
    comp_aux_num: str
    comp_aux_lib: str
    piece_ref: str
    piece_date: date | None
    ecriture_lib: str
    debit: float
    credit: float
    ecriture_let: str
    date_let: date | None
    valid_date: date | None
    montant_devise: float | None
    idevise: str


@dataclass
class AccountBalance:
    """Aggregated debit/credit totals for a single CompteNum."""
    compte_num: str
    compte_lib: str
    total_debit: float = 0.0
    total_credit: float = 0.0

    @property
    def solde(self) -> float:
        """Net balance: total_debit − total_credit.
        Positive = solde débiteur, negative = solde créditeur."""
        return self.total_debit - self.total_credit

    @property
    def solde_debiteur(self) -> float:
        return max(self.solde, 0.0)

    @property
    def solde_crediteur(self) -> float:
        return max(-self.solde, 0.0)


@dataclass
class FECResult:
    """Parsed FEC file: individual lines + per-account balance aggregates."""
    lines: list[FECLine]
    balances: dict[str, AccountBalance]   # keyed by CompteNum
    errors: list[str]
    encoding: str
    delimiter: str
    row_count: int

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def to_balances_dict(self) -> dict[str, float]:
        """
        Return {CompteNum: net_solde} as plain floats.
        This is the format consumed by ``services.reconciliation.reconcile()``.
        """
        return {num: bal.solde for num, bal in self.balances.items()}

    def balance(self, prefix: str) -> float:
        """Sum of net soldes for all accounts starting with *prefix*."""
        return sum(
            bal.solde
            for num, bal in self.balances.items()
            if num.startswith(prefix)
        )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_DATE_YYYYMMDD = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_DATE_ISO      = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DATE_DMY      = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_NEG_PAREN     = re.compile(r"^\(\s*(.+?)\s*\)$")
_THOUSANDS_SEP = re.compile(r"(?<=\d)[\s  ](?=\d)")


def _parse_date(raw: str) -> date | None:
    s = raw.strip()
    if not s:
        return None
    for pat, order in (
        (_DATE_YYYYMMDD, "ymd"),
        (_DATE_ISO,      "ymd"),
        (_DATE_DMY,      "dmy"),
    ):
        m = pat.match(s)
        if m:
            g = m.groups()
            try:
                if order == "ymd":
                    return date(int(g[0]), int(g[1]), int(g[2]))
                else:  # dmy
                    return date(int(g[2]), int(g[1]), int(g[0]))
            except ValueError:
                return None
    return None


def _parse_float(raw: str) -> float:
    """
    Parse a French or international number string to float.
    Returns 0.0 on empty / unparseable input.
    """
    s = str(raw).strip()
    if not s or s in {"-", "–", "—", "N/A", ""}:
        return 0.0

    negative = False
    m = _NEG_PAREN.match(s)
    if m:
        s = m.group(1)
        negative = True
    elif s.startswith("-"):
        s = s[1:]
        negative = True

    # Remove thousands separators (space variants)
    s = _THOUSANDS_SEP.sub("", s)
    s = s.replace(" ", "")

    # Normalise decimal: if both comma and dot are present, the last is decimal
    if "," in s and "." in s:
        # e.g. "1.234,56" → "1234.56"
        last_comma = s.rfind(",")
        last_dot   = s.rfind(".")
        if last_comma > last_dot:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return 0.0


def _parse_float_opt(raw: str) -> float | None:
    s = raw.strip()
    if not s:
        return None
    return _parse_float(s)


# ---------------------------------------------------------------------------
# Encoding & delimiter detection
# ---------------------------------------------------------------------------

def _detect_encoding(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"  # always succeeds


def _detect_delimiter(first_line: str) -> str:
    counts = {"|": first_line.count("|"),
              "\t": first_line.count("\t"),
              ";": first_line.count(";")}
    best = max(counts, key=lambda c: counts[c])
    return best if counts[best] >= 3 else "|"  # fall back to pipe


# ---------------------------------------------------------------------------
# Header normalisation
# ---------------------------------------------------------------------------

def _strip_bom(s: str) -> str:
    return s.lstrip("﻿").strip()


def _normalise_col(raw: str) -> str:
    """Map a raw header cell to the canonical column name (case-insensitive)."""
    clean = _strip_bom(raw).strip()
    for col in _COLUMNS:
        if col.lower() == clean.lower():
            return col
    return clean


# ---------------------------------------------------------------------------
# Core parsing function
# ---------------------------------------------------------------------------

def _parse_bytes(raw: bytes) -> FECResult:
    encoding = _detect_encoding(raw)
    text = raw.decode(encoding)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines_raw = text.split("\n")
    delimiter = _detect_delimiter(lines_raw[0]) if lines_raw else "|"

    reader = csv.DictReader(
        io.StringIO(text),
        delimiter=delimiter,
        restkey="_extra",
        restval="",
    )

    # Build canonical field name map from whatever the file's header says
    if reader.fieldnames is None:
        return FECResult(
            lines=[], balances={}, errors=["Fichier vide ou sans en-tête"],
            encoding=encoding, delimiter=delimiter, row_count=0,
        )

    col_map = {raw_col: _normalise_col(raw_col) for raw_col in reader.fieldnames}

    lines:    list[FECLine]              = []
    balances: dict[str, AccountBalance] = {}
    errors:   list[str]                 = []

    for row_num, raw_row in enumerate(reader, start=2):
        # Remap keys to canonical names
        row = {col_map.get(k, k): v for k, v in raw_row.items() if k != "_extra"}

        compte_num = row.get("CompteNum", "").strip()
        if not compte_num:
            errors.append(f"Ligne {row_num}: CompteNum vide — ignorée")
            continue

        try:
            debit  = _parse_float(row.get("Debit", ""))
            credit = _parse_float(row.get("Credit", ""))

            line = FECLine(
                journal_code    = row.get("JournalCode", "").strip(),
                journal_lib     = row.get("JournalLib", "").strip(),
                ecriture_num    = row.get("EcritureNum", "").strip(),
                ecriture_date   = _parse_date(row.get("EcritureDate", "")),
                compte_num      = compte_num,
                compte_lib      = row.get("CompteLib", "").strip(),
                comp_aux_num    = row.get("CompAuxNum", "").strip(),
                comp_aux_lib    = row.get("CompAuxLib", "").strip(),
                piece_ref       = row.get("PieceRef", "").strip(),
                piece_date      = _parse_date(row.get("PieceDate", "")),
                ecriture_lib    = row.get("EcritureLib", "").strip(),
                debit           = debit,
                credit          = credit,
                ecriture_let    = row.get("EcritureLet", "").strip(),
                date_let        = _parse_date(row.get("DateLet", "")),
                valid_date      = _parse_date(row.get("ValidDate", "")),
                montant_devise  = _parse_float_opt(row.get("Montantdevise", "")),
                idevise         = row.get("Idevise", "").strip(),
            )
            lines.append(line)

        except Exception as exc:  # noqa: BLE001
            errors.append(f"Ligne {row_num}: erreur inattendue — {exc}")
            continue

        # Aggregate balance
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
# Public class
# ---------------------------------------------------------------------------

class FECParser:
    """
    Parse a DGFiP FEC file from disk.

    Parameters
    ----------
    path : str | Path
        Path to the pipe-delimited .txt FEC file.

    Examples
    --------
    >>> result = FECParser("export_fec.txt").parse()
    >>> print(result.row_count)
    42318
    >>> print(result.balance("411"))    # net créances clients
    1_234_567.89
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def parse(self) -> FECResult:
        """Read and parse the FEC file.  Returns a :class:`FECResult`."""
        raw = self.path.read_bytes()
        return _parse_bytes(raw)

    @classmethod
    def from_bytes(cls, raw: bytes) -> FECResult:
        """Parse from raw bytes (useful when reading from Supabase Storage)."""
        return _parse_bytes(raw)
