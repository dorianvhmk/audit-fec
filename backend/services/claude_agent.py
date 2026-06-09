"""
claude_agent.py — Batch audit commentary generator.

Sends ALL non-OK reconciliation rows to claude-sonnet-4-6 in a SINGLE API call
using tool-use forced output, so the response is guaranteed-parseable JSON.

Usage
-----
    from services.claude_agent import generate_audit_commentaries
    from schemas import ReconciliationRow

    commentaries = generate_audit_commentaries(rows)
    # → [{"label": "...", "commentary": "...", "risk_level": "moyen"}, ...]

Only rows where status != "OK" are included in the output.
Returns an empty list when all rows are OK or when the input is empty.
"""

from __future__ import annotations

import json
import logging
import os
import sys

# Make sure backend root is on the path so `from schemas import …` and
# `from app.config import …` both resolve, regardless of how the module
# is imported.
_BACKEND = os.path.dirname(os.path.dirname(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import anthropic

from schemas import ReconciliationRow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """\
Tu es commissaire aux comptes (CAC) chargé d'un audit légal en France.
Tu analyses les écarts entre le FEC (Fichier des Écritures Comptables) et la
plaquette financière annuelle de l'entreprise auditée.

Pour chaque poste qui t'est soumis (statut "écart", "erreur" ou "absent"),
tu rédiges un commentaire d'audit en français en 1 à 2 phrases qui :
1. Identifie la cause probable de l'écart
2. Indique le niveau de risque d'audit : faible, moyen ou élevé
3. Propose une diligence d'audit concrète (circularisation, revue analytique, etc.)

Règles :
- Vocabulaire technique comptable français (PCG, normes ISA/NEP)
- Factuel et précis ; pas d'hypothèses non étayées par les chiffres
- Statut "absent" → risque minimum "moyen" (aucun compte FEC trouvé)
- Statut "erreur" (écart ≥ 5 %) → risque minimum "élevé"
- Statut "écart" (1–5 %) → évalue le risque selon le montant absolu
"""

# Tool that forces structured output — Claude MUST call this tool with every
# anomaly row filled in; the SDK then returns a guaranteed-parseable tool_input.
_SUBMIT_TOOL: dict = {
    "name": "soumettre_commentaires",
    "description": (
        "Soumettre les commentaires d'audit pour tous les postes analysés. "
        "Chaque entrée du tableau correspond exactement à un poste fourni, "
        "dans le même ordre."
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
                            "description": "Label exact du poste, identique à celui fourni.",
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
                            "description": "Niveau de risque d'audit.",
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
# Client (lazy singleton)
# ---------------------------------------------------------------------------

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        try:
            from app.config import settings  # type: ignore[import]
            api_key = settings.anthropic_api_key
        except Exception:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _fmt_amount(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:,.0f} €".replace(",", " ")  # narrow no-break space


def _build_user_message(rows: list[ReconciliationRow]) -> str:
    """Format all anomaly rows as a numbered list for the single batch call."""
    lines: list[str] = [
        f"Analyse des {len(rows)} poste(s) en anomalie :\n"
    ]
    for i, row in enumerate(rows, start=1):
        delta_str = (
            f"{row.delta_abs:+,.0f} € ({row.delta_pct:.1f} %)".replace(",", " ")
            if row.delta_abs is not None and row.delta_pct is not None
            else "N/D"
        )
        comptes = ", ".join(row.matched_accounts[:8])
        if len(row.matched_accounts) > 8:
            comptes += f" … (+{len(row.matched_accounts) - 8})"

        lines.append(
            f"[{i}] {row.label}\n"
            f"    Section     : {row.section}\n"
            f"    Plaquette N : {_fmt_amount(row.plaquette_amount)}\n"
            f"    FEC calculé : {_fmt_amount(row.fec_amount)}\n"
            f"    Écart       : {delta_str}\n"
            f"    Statut      : {row.status}\n"
            + (f"    Comptes FEC : {comptes}\n" if comptes else "")
        )
    lines.append(
        "\nUtilise l'outil `soumettre_commentaires` pour retourner "
        "un commentaire pour chacun des postes ci-dessus, dans le même ordre."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_audit_commentaries(
    rows: list[ReconciliationRow],
) -> list[dict]:
    """
    Generate French audit commentaries for all non-OK reconciliation rows
    in a single API call.

    Parameters
    ----------
    rows:
        Full list of reconciliation rows (OK rows are silently skipped).

    Returns
    -------
    list[dict]
        One entry per non-OK row:
        ``{"label": str, "commentary": str, "risk_level": "faible"|"moyen"|"élevé"}``
    """
    anomaly_rows = [r for r in rows if r.status != "OK"]
    if not anomaly_rows:
        return []

    client = _get_client()
    user_message = _build_user_message(anomaly_rows)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=[_SUBMIT_TOOL],
            tool_choice={"type": "tool", "name": "soumettre_commentaires"},
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        logger.error("Anthropic API error during commentary generation: %s", exc)
        return _fallback_commentaries(anomaly_rows, error=str(exc))

    # Extract the tool_use block — guaranteed present because we forced it.
    tool_input: dict | None = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "soumettre_commentaires":
            tool_input = block.input  # already a parsed dict via the SDK
            break

    if tool_input is None:
        logger.error(
            "No tool_use block in response (stop_reason=%s). Falling back.",
            response.stop_reason,
        )
        return _fallback_commentaries(anomaly_rows)

    raw_commentaires: list[dict] = tool_input.get("commentaires", [])

    # Build a label → result map for robust matching even if order drifts.
    result_by_label: dict[str, dict] = {
        c["label"]: c for c in raw_commentaires if isinstance(c, dict) and "label" in c
    }

    output: list[dict] = []
    for row in anomaly_rows:
        match = result_by_label.get(row.label)
        if match:
            output.append(
                {
                    "label": row.label,
                    "commentary": match.get("commentary", ""),
                    "risk_level": match.get("risk_level", "moyen"),
                }
            )
        else:
            # Row not returned by model (shouldn't happen, but be defensive).
            logger.warning("No commentary returned for label %r; using placeholder.", row.label)
            output.append(
                {
                    "label": row.label,
                    "commentary": "[Commentaire non disponible]",
                    "risk_level": "moyen",
                }
            )

    return output


# ---------------------------------------------------------------------------
# Fallback helper
# ---------------------------------------------------------------------------

def _fallback_commentaries(
    rows: list[ReconciliationRow],
    error: str = "",
) -> list[dict]:
    """Return placeholder commentaries when the API call fails."""
    suffix = f" Erreur technique : {error}" if error else ""
    return [
        {
            "label": row.label,
            "commentary": f"[Commentaire indisponible — génération échouée.{suffix}]",
            "risk_level": "moyen",
        }
        for row in rows
    ]
