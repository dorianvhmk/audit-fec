from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from app.services.supabase_store import create_analysis

router = APIRouter(prefix="/upload", tags=["upload"])

_MAX_SIZE = 50 * 1024 * 1024  # 50 MB

# Excel magic bytes (ZIP header) — same detection used in fec_parser.py
_XLSX_MAGIC = b"PK\x03\x04"

_ALLOWED_FEC_EXTENSIONS = {".xlsx", ".txt"}


def _is_xlsx_bytes(data: bytes) -> bool:
    return len(data) >= 4 and data[:4] == _XLSX_MAGIC


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
    # Accept .xlsx or .txt for the FEC file
    fname = (fec_file.filename or "").lower()
    if not any(fname.endswith(ext) for ext in _ALLOWED_FEC_EXTENSIONS):
        raise HTTPException(400, "Le fichier FEC doit être un .xlsx ou .txt")

    if not (pdf_file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "La plaquette doit être un .pdf")

    fec_bytes = await _read_limited(fec_file)
    pdf_bytes = await _read_limited(pdf_file)

    # Detect actual format from content (not just the filename extension)
    fec_is_xlsx = _is_xlsx_bytes(fec_bytes)
    fec_storage_name = "fec.xlsx" if fec_is_xlsx else "fec.txt"

    # Store raw files in Supabase Storage (bucket: audit-files)
    from app.services.supabase_store import _get_client
    analysis_id = create_analysis(client_name)

    sb = _get_client()
    sb.storage.from_("audit-files").upload(f"{analysis_id}/{fec_storage_name}", fec_bytes)
    sb.storage.from_("audit-files").upload(f"{analysis_id}/plaquette.pdf", pdf_bytes)

    return {"analysis_id": analysis_id, "status": "uploaded"}
