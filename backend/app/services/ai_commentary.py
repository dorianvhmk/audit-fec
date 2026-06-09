"""
Generate French audit commentary for each reconciliation row using Claude.
"""

from __future__ import annotations

import sys, os
_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import anthropic
from app.config import settings
from schemas import ReconciliationRow

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


_SYSTEM_PROMPT = """\
Tu es un expert-comptable et auditeur légal français. Tu rédiges des commentaires \
d'audit concis (2-3 phrases maximum) sur les écarts de rapprochement entre le FEC \
et la plaquette financière. Ton ton est professionnel et factuel. Tu utilises le \
vouvoiement institutionnel. Tu ne fais pas de suppositions non étayées par les chiffres.\
"""


def _build_user_prompt(row: ReconciliationRow) -> str:
    plaquette = f"{row.plaquette_amount:,.2f} €" if row.plaquette_amount is not None else "non disponible"
    fec = f"{row.fec_amount:,.2f} €" if row.fec_amount is not None else "non calculable"
    delta_str = f"{row.delta_abs:+,.2f} €" if row.delta_abs is not None else "N/A"
    pct_str = f"{row.delta_pct:.2f} %" if row.delta_pct is not None else "N/A"

    return (
        f"Poste : {row.label}\n"
        f"Section : {row.section}\n"
        f"Montant plaquette (N) : {plaquette}\n"
        f"Montant FEC calculé : {fec}\n"
        f"Écart absolu (FEC − plaquette) : {delta_str}\n"
        f"Écart relatif : {pct_str}\n"
        f"Statut : {row.status}\n\n"
        "Rédige un commentaire d'audit en français pour ce poste."
    )


def generate_commentary(row: ReconciliationRow) -> str:
    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(row)}],
    )
    return message.content[0].text.strip()


async def generate_commentaries_batch(rows: list[ReconciliationRow]) -> list[str]:
    """Generate commentary for all rows; on error, return a placeholder string."""
    import asyncio

    loop = asyncio.get_event_loop()
    results: list[str] = []
    for row in rows:
        try:
            comment = await loop.run_in_executor(None, generate_commentary, row)
        except Exception as exc:  # noqa: BLE001
            comment = f"[Erreur lors de la génération du commentaire : {exc}]"
        results.append(comment)
    return results
