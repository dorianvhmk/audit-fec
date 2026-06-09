import sys
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException

# Make backend/ importable so parsers/ and services/ resolve correctly.
_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.ai_commentary import generate_commentaries_batch
from app.services.supabase_store import update_analysis, get_analysis, _get_client
from parsers.fec_parser import FECParser
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

        sb = _get_client()
        # Try xlsx first (new uploads), fall back to txt (legacy records)
        try:
            fec_bytes = sb.storage.from_("audit-files").download(f"{analysis_id}/fec.xlsx")
        except Exception:
            fec_bytes = sb.storage.from_("audit-files").download(f"{analysis_id}/fec.txt")
        pdf_bytes = sb.storage.from_("audit-files").download(f"{analysis_id}/plaquette.pdf")

        fec_result = FECParser.from_bytes(fec_bytes)
        pdf_result = PDFExtractor.from_bytes(pdf_bytes)

        rows = reconcile(fec_result, pdf_result, MAPPING)
        comments = await generate_commentaries_batch(rows)

        results = {
            "rows": [_row_to_dict(r, c) for r, c in zip(rows, comments)],
            "fec_errors": fec_result.errors,
            "fec_row_count": fec_result.row_count,
            "pdf_sections": {k: v.get("confidence") for k, v in pdf_result.sections.items()},
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
