"""
Shared Pydantic schemas for the audit reconciliation API.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ReconciliationStatus = Literal["OK", "écart", "erreur", "absent"]


class ReconciliationRow(BaseModel):
    """One reconciled line item from a plaquette section."""

    label: str = Field(description="Line item label as extracted from the plaquette.")
    section: str = Field(
        description="Balance-sheet section: bilan_actif | bilan_passif | compte_de_resultat."
    )

    # Plaquette side
    plaquette_amount: float | None = Field(
        None, description="Amount from the plaquette (exercice N), in euros."
    )
    exercice_n1: float | None = Field(
        None, description="Prior-year amount from the plaquette (exercice N-1), for reference."
    )

    # Balance Générale side
    bg_amount: float | None = Field(
        None, description="Computed amount from Balance Générale using PCG mapping."
    )
    matched_accounts: list[str] = Field(
        default_factory=list,
        description="List of Compte values that contributed to bg_amount.",
    )
    pcg_prefixes_used: list[str] = Field(
        default_factory=list,
        description="PCG prefixes from mapping.py that were used to filter BG accounts.",
    )

    # Reconciliation result
    delta_abs: float | None = Field(
        None, description="Absolute delta: bg_amount − plaquette_amount."
    )
    delta_pct: float | None = Field(
        None,
        description=(
            "Relative delta as a percentage: |delta_abs / plaquette_amount| × 100. "
            "None when plaquette_amount is 0 or None."
        ),
    )
    status: ReconciliationStatus = Field(
        description=(
            "OK      — |delta%| < 1 %\n"
            "écart   — 1 % ≤ |delta%| < 5 %\n"
            "erreur  — |delta%| ≥ 5 %\n"
            "absent  — no BG accounts matched the PCG mapping"
        )
    )
    commentary: str = Field(
        default="",
        description="AI-generated French audit commentary (populated by ai_commentary service).",
    )
