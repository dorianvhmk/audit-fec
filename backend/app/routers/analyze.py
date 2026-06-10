import sys
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException

# Make backend/ importable so parsers/ and services/ resolve correctly.
_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.ai_commentary import generate_commentaries_batch
from app.services.supabase_store import (
    update_analysis,
    get_analysis,
    set_analysis_step,
    is_cancelled,
    _get_client as _get_supabase,
)
from parsers.bg_parser import BGParser
from parsers.fec_parser import FECParser   # kept for legacy Supabase records
from parsers.pdf_extractor import PDFExtractor
from parsers.mapping import MAPPING
from services.reconciliation import reconcile
from schemas import ReconciliationRow

router = APIRouter(prefix="/analyze", tags=["analyze"])


def _row_to_dict(row: ReconciliationRow, comment: str) -> dict:
    d = row.model_dump()
    d["commentary"] = comment
    return d


async def _run_analysis(analysis_id: str):
    try:
        update_analysis(analysis_id, "processing")
        sb = _get_supabase()

        # ── Step 1: Download + parse Balance Générale ────────────────────────
        set_analysis_step(analysis_id, "parsing_bg")
        try:
            # New uploads store bg.xlsx; fall back to legacy fec.xlsx / fec.txt
            try:
                bg_bytes = sb.storage.from_("audit-files").download(f"{analysis_id}/bg.xlsx")
                bg_result = BGParser.from_bytes(bg_bytes)
            except Exception:
                try:
                    bg_bytes = sb.storage.from_("audit-files").download(f"{analysis_id}/fec.xlsx")
                except Exception:
                    bg_bytes = sb.storage.from_("audit-files").download(f"{analysis_id}/fec.txt")
                bg_result = FECParser.from_bytes(bg_bytes)
        except Exception as dl_exc:
            raise RuntimeError(f"Téléchargement Balance Générale impossible : {dl_exc}") from dl_exc

        if is_cancelled(analysis_id):
            return  # status already set to "cancelled" by cancel_analysis()

        # ── Step 2: Download + extract PDF ──────────────────────────────────
        set_analysis_step(analysis_id, "extracting_pdf")
        pdf_bytes = sb.storage.from_("audit-files").download(f"{analysis_id}/plaquette.pdf")
        pdf_result = PDFExtractor.from_bytes(pdf_bytes)

        if is_cancelled(analysis_id):
            return

        # ── Step 3: Reconcile ────────────────────────────────────────────────
        set_analysis_step(analysis_id, "reconciling")
        rows = reconcile(bg_result, pdf_result, MAPPING)

        if is_cancelled(analysis_id):
            return

        # ── Step 4: Generate commentaries (single batch API call) ────────────
        set_analysis_step(analysis_id, "generating_comments")
        comments = await generate_commentaries_batch(rows)

        # ── Persist results ──────────────────────────────────────────────────
        results = {
            "rows":          [_row_to_dict(r, c) for r, c in zip(rows, comments)],
            "bg_errors":     bg_result.errors,
            "bg_row_count":  bg_result.row_count,
            "pdf_sections":  {k: v.get("confidence") for k, v in pdf_result.sections.items()},
        }
        update_analysis(analysis_id, "done", results)

    except Exception as exc:  # noqa: BLE001
        update_analysis(analysis_id, "error", {"error": str(exc)})


@router.post("/{analysis_id}")
async def start_analysis(analysis_id: str, background_tasks: BackgroundTasks):
    record = get_analysis(analysis_id)
    if not record:
        raise HTTPException(404, "Analyse introuvable")
    if record["status"] == "processing":
        raise HTTPException(409, "Analyse déjà en cours")

    background_tasks.add_task(_run_analysis, analysis_id)
    return {"analysis_id": analysis_id, "status": "processing"}
