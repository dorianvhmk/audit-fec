"""
FEC parser — DGFiP format, pipe-delimited, 18 mandatory columns.

Spec reference: Arrêté du 29 juillet 2013 (modifié 2014).

Column order (1-indexed):
 1  JournalCode
 2  JournalLib
 3  EcritureNum
 4  EcritureDate      YYYYMMDD
 5  CompteNum
 6  CompteLib
 7  CompAuxNum        (optionnel, peut être vide)
 8  CompAuxLib        (optionnel, peut être vide)
 9  PieceRef
10  PieceDate         YYYYMMDD
11  EcritureLib
12  Debit             décimal, séparateur virgule ou point
13  Credit            décimal, séparateur virgule ou point
14  EcritureLet       (optionnel)
15  DateLet           (optionnel)
16  ValidDate         YYYYMMDD
17  Montantdevise     (optionnel)
18  Idevise           (optionnel)
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterator

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

FEC_COLUMNS = [
    "JournalCode", "JournalLib", "EcritureNum", "EcritureDate",
    "CompteNum", "CompteLib", "CompAuxNum", "CompAuxLib",
    "PieceRef", "PieceDate", "EcritureLib",
    "Debit", "Credit",
    "EcritureLet", "DateLet", "ValidDate",
    "Montantdevise", "Idevise",
]


@dataclass
class FecLine:
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
    debit: Decimal
    credit: Decimal
    ecriture_let: str
    date_let: date | None
    valid_date: date | None
    montant_devise: Decimal | None
    idevise: str


@dataclass
class AccountBalance:
    compte_num: str
    compte_lib: str
    total_debit: Decimal = field(default_factory=Decimal)
    total_credit: Decimal = field(default_factory=Decimal)

    @property
    def solde(self) -> Decimal:
        """Solde débiteur net (positif = solde débiteur, négatif = solde créditeur)."""
        return self.total_debit - self.total_credit

    @property
    def solde_debiteur(self) -> Decimal:
        return max(self.solde, Decimal(0))

    @property
    def solde_crediteur(self) -> Decimal:
        return max(-self.solde, Decimal(0))


@dataclass
class FecParseResult:
    lines: list[FecLine]
    balances: dict[str, AccountBalance]   # keyed by CompteNum
    errors: list[str]
    encoding_detected: str
    row_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(r"^\d{8}$")


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw or not _DATE_PATTERN.match(raw):
        return None
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None


def _parse_decimal(raw: str) -> Decimal:
    """Accept both '1234,56' and '1234.56' formats."""
    raw = raw.strip().replace("\xa0", "").replace(" ", "")
    if not raw:
        return Decimal(0)
    raw = raw.replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal(0)


def _parse_decimal_opt(raw: str) -> Decimal | None:
    raw = raw.strip()
    if not raw:
        return None
    return _parse_decimal(raw)


def _detect_encoding(raw_bytes: bytes) -> str:
    """
    DGFiP files are commonly ISO-8859-1 (Latin-1) or UTF-8 with BOM.
    We try UTF-8-sig first, fall back to latin-1 which never raises.
    """
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            raw_bytes.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _detect_delimiter(first_line: str) -> str:
    """
    FEC spec mandates pipe '|' but some exporters use tab or semicolon.
    Count occurrences of each candidate on the header line.
    """
    candidates = {"|": 0, "\t": 0, ";": 0}
    for ch, _ in candidates.items():
        candidates[ch] = first_line.count(ch)
    return max(candidates, key=lambda c: candidates[c])


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _iter_rows(text: str, delimiter: str) -> Iterator[dict[str, str]]:
    reader = csv.DictReader(
        io.StringIO(text),
        delimiter=delimiter,
        restkey="_extra",
        restval="",
    )
    # Normalise header keys: strip BOM, whitespace, and map to canonical names
    # DGFiP header may include accented chars in older exports; we match
    # case-insensitively against the canonical list.
    if reader.fieldnames is None:
        return

    canonical_map: dict[str, str] = {}
    for raw_key in reader.fieldnames:
        clean = raw_key.strip().lstrip("﻿")
        matched = next(
            (col for col in FEC_COLUMNS if col.lower() == clean.lower()),
            clean,
        )
        canonical_map[raw_key] = matched

    for row in reader:
        yield {canonical_map.get(k, k): v for k, v in row.items() if k != "_extra"}


def parse_fec(raw_bytes: bytes) -> FecParseResult:
    """
    Parse a DGFiP FEC file from raw bytes.

    Returns a FecParseResult with individual lines and aggregated
    per-account balances (suitable for reconciliation).
    """
    encoding = _detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding)

    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    first_line = text.split("\n")[0]
    delimiter = _detect_delimiter(first_line)

    lines: list[FecLine] = []
    errors: list[str] = []
    balances: dict[str, AccountBalance] = {}

    for i, row in enumerate(_iter_rows(text, delimiter), start=2):  # row 1 = header
        try:
            compte_num = row.get("CompteNum", "").strip()
            if not compte_num:
                errors.append(f"Ligne {i}: CompteNum vide, ignorée")
                continue

            debit = _parse_decimal(row.get("Debit", ""))
            credit = _parse_decimal(row.get("Credit", ""))

            fec_line = FecLine(
                journal_code=row.get("JournalCode", "").strip(),
                journal_lib=row.get("JournalLib", "").strip(),
                ecriture_num=row.get("EcritureNum", "").strip(),
                ecriture_date=_parse_date(row.get("EcritureDate", "")),
                compte_num=compte_num,
                compte_lib=row.get("CompteLib", "").strip(),
                comp_aux_num=row.get("CompAuxNum", "").strip(),
                comp_aux_lib=row.get("CompAuxLib", "").strip(),
                piece_ref=row.get("PieceRef", "").strip(),
                piece_date=_parse_date(row.get("PieceDate", "")),
                ecriture_lib=row.get("EcritureLib", "").strip(),
                debit=debit,
                credit=credit,
                ecriture_let=row.get("EcritureLet", "").strip(),
                date_let=_parse_date(row.get("DateLet", "")),
                valid_date=_parse_date(row.get("ValidDate", "")),
                montant_devise=_parse_decimal_opt(row.get("Montantdevise", "")),
                idevise=row.get("Idevise", "").strip(),
            )
            lines.append(fec_line)

            # Aggregate balance per account
            if compte_num not in balances:
                balances[compte_num] = AccountBalance(
                    compte_num=compte_num,
                    compte_lib=fec_line.compte_lib,
                    total_debit=Decimal(0),
                    total_credit=Decimal(0),
                )
            balances[compte_num].total_debit += debit
            balances[compte_num].total_credit += credit

        except Exception as exc:  # noqa: BLE001
            errors.append(f"Ligne {i}: erreur inattendue — {exc}")

    return FecParseResult(
        lines=lines,
        balances=balances,
        errors=errors,
        encoding_detected=encoding,
        row_count=len(lines),
    )


# ---------------------------------------------------------------------------
# Aggregation helpers used by the reconciliation service
# ---------------------------------------------------------------------------

def balances_by_class(result: FecParseResult) -> dict[str, Decimal]:
    """
    Return net solde grouped by PCG account class (first digit of CompteNum).
    Solde = total_debit - total_credit (positive = débiteur).
    """
    by_class: dict[str, Decimal] = {}
    for acc in result.balances.values():
        cls = acc.compte_num[0] if acc.compte_num else "?"
        by_class[cls] = by_class.get(cls, Decimal(0)) + acc.solde
    return by_class


def balances_by_prefix(result: FecParseResult, prefix_len: int = 3) -> dict[str, Decimal]:
    """
    Return net solde grouped by CompteNum prefix of given length.
    Useful for matching plaquette line items (e.g. '211' → immobilisations).
    """
    by_prefix: dict[str, Decimal] = {}
    for acc in result.balances.values():
        prefix = acc.compte_num[:prefix_len].ljust(prefix_len, "0")
        by_prefix[prefix] = by_prefix.get(prefix, Decimal(0)) + acc.solde
    return by_prefix
