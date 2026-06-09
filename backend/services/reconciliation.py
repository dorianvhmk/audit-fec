"""
Reconciliation engine.

Public signature
----------------
    from parsers.fec_parser   import FECParser
    from parsers.pdf_extractor import PDFExtractor
    from parsers.mapping       import MAPPING
    from services.reconciliation import reconcile

    fec  = FECParser("fec.txt").parse()
    pdf  = PDFExtractor("plaquette.pdf").extract()
    rows = reconcile(fec, pdf, MAPPING)

Parameters
----------
fec     : FECResult   — output of FECParser.parse()
pdf     : PDFResult   — output of PDFExtractor.extract()
mapping : dict[str, list[str]]
              Label → list of CompteNum prefixes.
              Typically ``parsers.mapping.MAPPING``, but a custom dict can be
              passed to override or extend coverage.

Returns
-------
list[ReconciliationRow]   (defined in schemas.py)

Status thresholds
-----------------
  OK     |delta%| < 1 %
  écart  1 % ≤ |delta%| < 5 %
  erreur |delta%| ≥ 5 %
  absent no FEC accounts matched OR plaquette_amount is None

Sign convention
---------------
FEC soldes are (total_debit − total_credit).  Because the plaquette always
shows positive figures we compare ``abs(fec_sum)`` against the plaquette
amount.  This works for all cases:
  • Net assets  : sum(debit) + sum(contra credit) → correct net
  • Liabilities : credit-balance accounts → negative solde → abs → positive
  • Revenue     : credit solde → abs → positive
  • Expense     : debit solde → positive already
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from parsers.mapping import find_prefixes, find_section
from schemas import ReconciliationRow, ReconciliationStatus

# Forward-declare the imported types for type hints without circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from parsers.fec_parser    import FECResult
    from parsers.pdf_extractor import PDFResult

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_THRESHOLD_OK    = 1.0   # percent
_THRESHOLD_ECART = 5.0   # percent

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sum_fec(
    balances: dict[str, float],
    prefixes: list[str],
) -> tuple[float, list[str]]:
    """Sum net soldes for every account whose CompteNum starts with any prefix."""
    total   = 0.0
    matched: list[str] = []
    for compte_num, solde in balances.items():
        if any(compte_num.startswith(p) for p in prefixes):
            total += solde
            matched.append(compte_num)
    return total, sorted(matched)


def _status(delta_pct: float | None) -> ReconciliationStatus:
    if delta_pct is None:
        return "absent"
    if delta_pct < _THRESHOLD_OK:
        return "OK"
    if delta_pct < _THRESHOLD_ECART:
        return "écart"
    return "erreur"


def _make_absent(
    label: str,
    section: str,
    plaquette_amount: float | None,
    exercice_n1: float | None,
    fec_amount: float | None,
    matched: list[str],
    prefixes: list[str],
) -> ReconciliationRow:
    return ReconciliationRow(
        label=label,
        section=section,
        plaquette_amount=plaquette_amount,
        exercice_n1=exercice_n1,
        fec_amount=fec_amount,
        matched_accounts=matched,
        pcg_prefixes_used=prefixes,
        delta_abs=None,
        delta_pct=None,
        status="absent",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconcile(
    fec:     "FECResult",
    pdf:     "PDFResult",
    mapping: dict[str, list[str]],
) -> list[ReconciliationRow]:
    """
    Reconcile a parsed FEC against a parsed plaquette using *mapping*.

    Each plaquette row becomes one :class:`~schemas.ReconciliationRow`.
    Rows that are pure section headers (no plaquette amount) are included
    with status ``"absent"`` so they remain visible in the output table.

    Parameters
    ----------
    fec :
        Result of ``FECParser(...).parse()``.
    pdf :
        Result of ``PDFExtractor(...).extract()``.
    mapping :
        ``{canonical_label: [pcg_prefix, ...]}``.  Fuzzy-matched against
        the plaquette label — pass ``MAPPING`` from ``parsers.mapping`` for
        the built-in 80-entry mapping, or a custom dict to override.

    Returns
    -------
    list[ReconciliationRow]
    """
    # Flat {CompteNum: net_solde} dict — built once, reused for every row
    fec_balances: dict[str, float] = fec.to_balances_dict()

    rows: list[ReconciliationRow] = []

    for section_key, section_data in pdf.sections.items():
        for plaquette_row in section_data.get("rows", []):
            label: str = plaquette_row.get("label", "").strip()
            if not label:
                continue

            exercice_n:  float | None = plaquette_row.get("exercice_n")
            exercice_n1: float | None = plaquette_row.get("exercice_n1")

            # Prefer the mapping's own section over the PDF-detected section
            section  = find_section(label) or section_key
            prefixes = find_prefixes(label, mapping)

            # ── No mapping found ──────────────────────────────────────────
            if not prefixes:
                rows.append(_make_absent(label, section, exercice_n, exercice_n1,
                                         None, [], []))
                continue

            raw_fec, matched = _sum_fec(fec_balances, prefixes)

            # ── No FEC accounts matched the prefixes ──────────────────────
            if not matched:
                rows.append(_make_absent(label, section, exercice_n, exercice_n1,
                                         None, [], prefixes))
                continue

            fec_amount = abs(raw_fec)   # plaquette figures are always positive

            # ── Section header row (no plaquette amount) ──────────────────
            if exercice_n is None:
                rows.append(_make_absent(label, section, None, exercice_n1,
                                         fec_amount, matched, prefixes))
                continue

            # ── Normal reconciliation ─────────────────────────────────────
            delta_abs = fec_amount - exercice_n

            if exercice_n != 0.0:
                delta_pct = round(abs(delta_abs / exercice_n) * 100.0, 4)
            else:
                delta_pct = 0.0 if fec_amount == 0.0 else 100.0

            rows.append(ReconciliationRow(
                label            = label,
                section          = section,
                plaquette_amount = exercice_n,
                exercice_n1      = exercice_n1,
                fec_amount       = round(fec_amount, 2),
                matched_accounts = matched,
                pcg_prefixes_used= prefixes,
                delta_abs        = round(delta_abs, 2),
                delta_pct        = delta_pct,
                status           = _status(delta_pct),
            ))

    return rows
