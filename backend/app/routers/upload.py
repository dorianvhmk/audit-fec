from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from app.services.supabase_store import create_analysis

router = APIRouter(prefix="/upload", tags=["upload"])

_MAX_SIZE = 50 * 1024 * 1024  # 50 MB


async def _read_limited(file: UploadFile) -> bytes:
    data = await file.read(_MAX_SIZE + 1)
    if len(data) > _MAX_SIZE:
        raise HTTPException(413, "Fichier trop volumineux (max 50 Mo)")
    return data


@router.post("")
async def upload_files(
    client_name: str = Form(...),
    fec_file: UploadFile = File(...),
    pdf_file: UploadFile = File(...),
):
    if not fec_file.filename.endswith(".txt"):
        raise HTTPException(400, "Le fichier FEC doit être un .txt")
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "La plaquette doit être un .pdf")

    fec_bytes = await _read_limited(fec_file)
    pdf_bytes = await _read_limited(pdf_file)

    # Store raw files temporarily in Supabase Storage (bucket: audit-files)
    from app.services.supabase_store import _get_client
    analysis_id = create_analysis(client_name)

    sb = _get_client()
    sb.storage.from_("audit-files").upload(f"{analysis_id}/fec.txt", fec_bytes)
    sb.storage.from_("audit-files").upload(f"{analysis_id}/plaquette.pdf", pdf_bytes)

    return {"analysis_id": analysis_id, "status": "uploaded"}
