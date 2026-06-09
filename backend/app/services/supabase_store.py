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
