"""
Supabase persistence layer.

Table schema (run in Supabase SQL editor):

    create table if not exists analyses (
        id          uuid primary key default gen_random_uuid(),
        client_name text not null,
        created_at  timestamptz default now(),
        status      text default 'pending',   -- pending | processing | done | error
        results     jsonb
    );
"""

from __future__ import annotations

import uuid
from typing import Any

from supabase import create_client, Client
from app.config import settings

# ---------------------------------------------------------------------------
# In-process step tracker (background task and HTTP handler share the same
# process on Railway, so a module-level dict is sufficient)
# ---------------------------------------------------------------------------

#: Human-readable step labels — order defines the progress bar sequence.
STEP_LABELS: dict[str, str] = {
    "parsing_bg":          "Lecture de la Balance Générale",
    "extracting_pdf":      "Extraction de la plaquette PDF",
    "reconciling":         "Rapprochement des données",
    "generating_comments": "Génération des commentaires IA",
}

_step_registry: dict[str, str] = {}  # analysis_id → current step key


def set_analysis_step(analysis_id: str, step: str) -> None:
    """Record the current pipeline step for an in-flight analysis."""
    _step_registry[analysis_id] = step


def get_analysis_step(analysis_id: str) -> str | None:
    """Return the current step key, or None if not yet set / already done."""
    return _step_registry.get(analysis_id)


# ---------------------------------------------------------------------------
# In-process cancellation registry
# ---------------------------------------------------------------------------

_cancel_registry: dict[str, bool] = {}  # analysis_id → True if cancelled


def cancel_analysis(analysis_id: str) -> None:
    """
    Mark an analysis for cancellation and persist the status to Supabase.

    Sets the in-process flag immediately (so the pipeline stops at the next
    checkpoint) then writes status="cancelled" to the database.
    """
    _cancel_registry[analysis_id] = True
    # update_analysis is defined below — forward reference resolved at call time
    update_analysis(analysis_id, "cancelled")


def is_cancelled(analysis_id: str) -> bool:
    """Return True if the analysis has been cancelled."""
    return _cancel_registry.get(analysis_id, False)


_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


def create_analysis(client_name: str) -> str:
    """Insert a new pending analysis and return its UUID."""
    sb = _get_client()
    data = sb.table("analyses").insert({"client_name": client_name, "status": "pending"}).execute()
    return data.data[0]["id"]


def update_analysis(analysis_id: str, status: str, results: Any | None = None) -> None:
    sb = _get_client()
    payload: dict[str, Any] = {"status": status}
    if results is not None:
        payload["results"] = results
    sb.table("analyses").update(payload).eq("id", analysis_id).execute()


def get_analysis(analysis_id: str) -> dict | None:
    sb = _get_client()
    data = sb.table("analyses").select("*").eq("id", analysis_id).single().execute()
    return data.data


def list_analyses(limit: int = 50) -> list[dict]:
    """Return the most recent analyses (lightweight — no results JSONB)."""
    sb = _get_client()
    data = (
        sb.table("analyses")
        .select("id, client_name, status, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return data.data or []
