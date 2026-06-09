import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import openpyxl
from openpyxl.styles import PatternFill, Font

from app.services.supabase_store import get_analysis, list_analyses

router = APIRouter(tags=["results"])

_STATUS_COLORS = {
    "OK":     "C6EFCE",  # green
    "écart":  "FFEB9C",  # yellow
    "erreur": "FFC7CE",  # red
    "absent": "E0E0E0",  # gray
}


@router.get("/analyses")
def get_analyses():
    """List the 50 most recent analyses (id, client_name, status, created_at)."""
    return list_analyses(limit=50)


@router.get("/results/{analysis_id}")
def get_results(analysis_id: str):
    record = get_analysis(analysis_id)
    if not record:
        raise HTTPException(404, "Analyse introuvable")
    return record


@router.get("/export/{analysis_id}")
def export_excel(analysis_id: str):
    record = get_analysis(analysis_id)
    if not record:
        raise HTTPException(404, "Analyse introuvable")
    if record["status"] != "done" or not record.get("results"):
        raise HTTPException(400, "Analyse non terminée")

    rows = record["results"].get("rows", [])
    client_name = record.get("client_name", "")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rapprochement"

    headers = ["Poste", "Section", "Montant plaquette", "Montant FEC", "Écart (€)", "Écart (%)", "Statut", "Commentaire"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in rows:
        status = row.get("status", "")
        ws.append([
            row.get("label"),
            row.get("section"),
            row.get("plaquette_amount"),
            row.get("fec_amount"),
            row.get("delta_abs"),
            row.get("delta_pct"),
            status,
            row.get("commentary"),
        ])
        fill_color = _STATUS_COLORS.get(status, "FFFFFF")
        fill = PatternFill(fill_type="solid", fgColor=fill_color)
        for cell in ws[ws.max_row]:
            cell.fill = fill

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["G"].width = 60

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_name = "".join(c for c in client_name if c.isalnum() or c in " _-")
    filename = f"rapprochement_{safe_name}.xlsx".replace(" ", "_")

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
