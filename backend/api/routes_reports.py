"""Report export (README's "Phase C"): renders an already-assembled,
already-edited block list (see src/reports/models.py) to one of 8 formats.
This route never touches DATASET.xlsx or re-derives KPIs/charts/tables --
the frontend already fetched and, if the user edited the preview, already
changed everything in the payload; this endpoint only lays it out.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response

from src.reports.chart_image import ChartRenderError
from src.reports.dispatch import RENDERERS
from src.reports.models import ReportPayload

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/render")
def render_report(format: str, payload: ReportPayload):
    spec = RENDERERS.get(format)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"Unknown format: {format!r}. Choose one of {sorted(RENDERERS)}.")

    try:
        content = spec.render(payload)
    except ChartRenderError as error:
        raise HTTPException(status_code=503, detail=str(error))

    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in payload.meta.title).strip() or "report"
    filename = f"{safe_title}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{spec.extension}"
    return Response(
        content=content,
        media_type=spec.content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
