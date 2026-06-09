"""
Reconciliation engine.

For each plaquette line:
  1. Look up PCG prefixes via pcg_mapping.
  2. Sum FEC net soldes for matching accounts.
  3. Compute delta = fec_amount - plaquette_amount.
  4. Assign status: OK (|delta| <= threshold), écart, or absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.services.fec_parser import FecParseResult, AccountBalance
from app.services.pdf_extractor import PlaquetteLine, TableType
from app.services.pcg_mapping import prefixes_for_label

Status = Literal["OK", "écart", "absent"]

DELTA_THRESHOLD = Decimal("1")   # 1 € tolerance for rounding differences


@dataclass
class ReconciliationRow:
    label: str
    table_type: str
    plaquette_amount: Decimal | None
    fec_amount: Decimal | None
    delta: Decimal | None          # fec - plaquette (None if absent)
    status: Status
    matched_accounts: list[str]    # CompteNum list that contributed to fec_amount
    pcg_prefixes_used: list[str]


def _sum_fec_for_prefixes(
    balances: dict[str, AccountBalance],
    prefixes: list[str],
    section: str,
) -> tuple[Decimal, list[str]]:
    """
    Sum net soldes of FEC accounts whose CompteNum starts with any of the
    given prefixes.  For actif/passif we use absolute solde; for resultat
    we use raw solde (debit - credit).
    """
    total = Decimal(0)
    matched: list[str] = []

    for compte_num, balance in balances.items():
        if any(compte_num.startswith(p) for p in prefixes):
            if section == "resultat":
                total += balance.solde
            elif section == "actif":
                # Actif accounts are normally debit; we take absolute value
                total += abs(balance.solde)
            else:  # passif
                total += abs(balance.solde)
            matched.append(compte_num)

    return total, sorted(matched)


def _section_for_table_type(table_type: TableType) -> str:
    mapping = {
        TableType.BILAN_ACTIF: "actif",
        TableType.BILAN_PASSIF: "passif",
        TableType.COMPTE_RESULTAT: "resultat",
        TableType.UNKNOWN: "",
    }
    return mapping[table_type]


def reconcile(
    fec_result: FecParseResult,
    plaquette_lines: list[PlaquetteLine],
) -> list[ReconciliationRow]:
    rows: list[ReconciliationRow] = []

    for pl_line in plaquette_lines:
        section = _section_for_table_type(pl_line.table_type)
        prefixes = prefixes_for_label(pl_line.label, section or None)

        if not prefixes:
            # No PCG mapping found — still include row as "absent"
            rows.append(ReconciliationRow(
                label=pl_line.label,
                table_type=pl_line.table_type.value,
                plaquette_amount=pl_line.montant_n,
                fec_amount=None,
                delta=None,
                status="absent",
                matched_accounts=[],
                pcg_prefixes_used=[],
            ))
            continue

        fec_amount, matched_accounts = _sum_fec_for_prefixes(
            fec_result.balances, prefixes, section
        )

        plaquette_amount = pl_line.montant_n

        if plaquette_amount is None:
            status: Status = "absent"
            delta = None
        else:
            delta = fec_amount - plaquette_amount
            status = "OK" if abs(delta) <= DELTA_THRESHOLD else "écart"

        rows.append(ReconciliationRow(
            label=pl_line.label,
            table_type=pl_line.table_type.value,
            plaquette_amount=plaquette_amount,
            fec_amount=fec_amount if matched_accounts else None,
            delta=delta,
            status=status,
            matched_accounts=matched_accounts,
            pcg_prefixes_used=prefixes,
        ))

    return rows
