"""
Batch French audit commentary generation using Claude (single API call).

All non-OK reconciliation rows are sent in ONE Anthropic API call using
forced tool-use output — no per-row calls, no asyncio loops.

Public interface (unchanged for analyze.py):
    await generate_commentaries_batch(rows) → list[str]
    Returns one commentary string per row in the SAME ORDER as `rows`.
    OK rows receive "". All anomalies are covered in the single batch call.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import anthropic
from app.config import settings
from schemas import ReconciliationRow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """\
Tu es commissaire aux comptes (CAC) chargé d'un audit légal en France.
Tu analyses les écarts entre la Balance Générale (BG) et la plaquette
financière annuelle de l'entreprise auditée.

Pour chaque poste qui t'est soumis (statut "écart", "erreur" ou "absent"),
tu rédiges un commentaire d'audit en français en 1 à 2 phrases qui :
1. Identifie la cause probable de l'écart
2. Indique le niveau de risque d'audit : faible, moyen ou élevé
3. Propose une diligence d'audit concrète (circularisation, revue analytique, etc.)

Règles :
- Vocabulaire technique comptable français (PCG, normes ISA/NEP)
- Factuel et précis ; pas d'hypothèses non étayées par les chiffres
- Statut "absent" → risque minimum "moyen" (aucun compte BG trouvé)
- Statut "erreur" (écart ≥ 5 %) → risque minimum "élevé"
- Statut "écart" (1–5 %) → évalue le risque selon le montant absolu
"""

# Forced tool-use schema — Claude MUST fill every slot in the array.
_SUBMIT_TOOL: dict = {
    "name": "soumettre_commentaires",
    "description": (
        "Soumettre les commentaires d'audit pour tous les postes analysés. "
        "Chaque entrée correspond à un poste fourni, dans le même ordre."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "commentaires": {
                "type": "array",
                "description": "Un commentaire par poste, dans le même ordre que la liste fournie.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {
                            "type": "string",
                            "description": "Label exact du poste (identique à celui fourni).",
                        },
                        "commentary": {
                            "type": "string",
                            "description": (
                                "Commentaire d'audit en 1-2 phrases : cause probable, "
                                "niveau de risque (faible/moyen/élevé), diligence recommandée."
                            ),
                        },
                        "risk_level": {
                            "type": "string",
                            "enum": ["faible", "moyen", "élevé"],
                        },
                    },
                    "required": ["label", "commentary", "risk_level"],
                },
            }
        },
        "required": ["commentaires"],
    },
}

# ---------------------------------------------------------------------------
# Anthropic client (lazy singleton)
# ---------------------------------------------------------------------------

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _fmt_amount(v: float | None) -> str:
    return "N/D" if v is None else f"{v:,.0f} €".replace(",", " ")


def _build_prompt(rows: list[ReconciliationRow]) -> str:
    lines: list[str] = [f"Analyse des {len(rows)} poste(s) en anomalie :\n"]
    for i, row in enumerate(rows, start=1):
        if row.delta_abs is not None and row.delta_pct is not None:
            delta = (
                f"{row.delta_abs:+,.0f} € ({row.delta_pct:.1f} %)"
                .replace(",", " ")
            )
        else:
            delta = "N/D"
        comptes = ", ".join(row.matched_accounts[:8])
        if len(row.matched_accounts) > 8:
            comptes += f" … (+{len(row.matched_accounts) - 8})"

        lines.append(
            f"[{i}] {row.label}\n"
            f"    Section     : {row.section}\n"
            f"    Plaquette N : {_fmt_amount(row.plaquette_amount)}\n"
            f"    BG calculé  : {_fmt_amount(row.bg_amount)}\n"
            f"    Écart       : {delta}\n"
            f"    Statut      : {row.status}\n"
            + (f"    Comptes FEC : {comptes}\n" if comptes else "")
        )
    lines.append(
        "\nUtilise l'outil `soumettre_commentaires` pour retourner "
        "un commentaire pour chacun des postes ci-dessus, dans le même ordre."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Single batch Claude call (synchronous — run in executor from async context)
# ---------------------------------------------------------------------------

def _call_claude_batch(anomaly_rows: list[ReconciliationRow]) -> dict[str, str]:
    """
    Call Claude once with all anomaly rows.
    Returns {label: commentary} mapping.
    Falls back to placeholder strings on API error.
    """
    client = _get_client()
    prompt = _build_prompt(anomaly_rows)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=[_SUBMIT_TOOL],
            tool_choice={"type": "tool", "name": "soumettre_commentaires"},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        logger.error("Anthropic API error during batch commentary: %s", exc)
        return {
            row.label: f"[Commentaire indisponible — erreur API: {exc}]"
            for row in anomaly_rows
        }

    # Extract tool_use block — guaranteed present because we forced it
    tool_input: dict | None = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "soumettre_commentaires":
            tool_input = block.input
            break

    if tool_input is None:
        logger.error(
            "No tool_use block returned (stop_reason=%s). Using placeholders.",
            response.stop_reason,
        )
        return {row.label: "[Commentaire non disponible]" for row in anomaly_rows}

    raw: list[dict] = tool_input.get("commentaires", [])

    # Build label → commentary dict (order-safe via label key)
    result: dict[str, str] = {}
    for item in raw:
        if isinstance(item, dict) and "label" in item:
            result[item["label"]] = item.get("commentary", "[vide]")

    # Fill any gaps (label not returned by model)
    for row in anomaly_rows:
        if row.label not in result:
            logger.warning("No commentary returned for %r — using placeholder.", row.label)
            result[row.label] = "[Commentaire non disponible]"

    return result


# ---------------------------------------------------------------------------
# Public async interface (called by analyze.py)
# ---------------------------------------------------------------------------

async def generate_commentaries_batch(rows: list[ReconciliationRow]) -> list[str]:
    """
    Generate audit commentaries for all rows in a single API call.

    Parameters
    ----------
    rows : list[ReconciliationRow]
        All reconciliation rows (OK rows are silently skipped and receive "").

    Returns
    -------
    list[str]
        One commentary string per row, same order as `rows`.
        OK rows → empty string.
        All anomaly rows handled in one Anthropic API call.
    """
    anomaly_rows = [r for r in rows if r.status != "OK"]
    if not anomaly_rows:
        return [""] * len(rows)

    # Run the synchronous Claude call off the event loop thread
    loop = asyncio.get_event_loop()
    comment_map = await loop.run_in_executor(None, _call_claude_batch, anomaly_rows)

    return [comment_map.get(row.label, "") for row in rows]
