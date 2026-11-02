from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import EXPORT_DIR, PREVIEW_DIR, PROJECT_MEDIA_DIR
from ..db import get_db
from ..services.ffmpeg_tools import extract_thumbnail
from ..services.render_jobs import get_export, request_cancel
from ..services.serializers import export_out
from ..utils.security import is_within, media_path, relative_to_media
from .helpers import thumbnail_file

router = APIRouter(prefix="/api/exports", tags=["exports"])


def _get_project(project_id: str | None) -> dict | None:
    if not project_id:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


@router.get("")
def list_exports(
    type: str | None = None,
    status: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
) -> dict:
    clauses: list[str] = []
    params: list[str | int] = []
    if type:
        clauses.append("e.type = ?")
        params.append(type)
    if status:
        clauses.append("e.status = ?")
        params.append(status)
    if project_id:
        clauses.append("e.project_id = ?")
        params.append(project_id)
    query = """
        SELECT e.*, p.name AS project_name, p.thumbnail_path AS project_thumbnail
        FROM exports e LEFT JOIN projects p ON p.id = e.project_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY e.created_at DESC LIMIT ?"
    params.append(max(1, min(limit, 500)))
    with get_db() as db:
        rows = db.execute(query, params).fetchall()
    return {
        "exports": [
            {
                **export_out(dict(row)),
                "project_name": row["project_name"],
            }
            for row in rows
        ]
    }


@router.get("/{export_id}")
def read_export(export_id: str) -> dict:
    row = get_export(export_id)
    if not row:
        raise HTTPException(status_code=404, detail="Export not found")
    project = _get_project(row.get("project_id"))
    return {
        **export_out(row),
        "project_name": project["name"] if project else None,
    }


@router.get("/{export_id}/file")
def download_export(export_id: str) -> FileResponse:
    row = get_export(export_id)
    if not row:
        raise HTTPException(status_code=404, detail="Export not found")
    if row["status"] != "completed" or not row.get("output_path"):
        raise HTTPException(status_code=409, detail="Export is not complete yet")
    try:
        path = media_path(row["output_path"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Export file is unavailable") from exc
    if not (is_within(path, EXPORT_DIR) or is_within(path, PREVIEW_DIR)) or not path.exists():
        raise HTTPException(status_code=404, detail="Export file is missing")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )


@router.get("/{export_id}/thumbnail")
def export_thumbnail(export_id: str) -> FileResponse:
    row = get_export(export_id)
    if not row:
        raise HTTPException(status_code=404, detail="Export not found")
    project = _get_project(row.get("project_id"))
    if project:
        try:
            return FileResponse(thumbnail_file(project), media_type="image/jpeg")
        except HTTPException:
            pass
    # Generate a poster for a video export if the project has no thumbnail yet.
    if row["status"] == "completed" and row.get("output_path"):
        try:
            path = media_path(row["output_path"])
        except ValueError:
            raise HTTPException(status_code=404, detail="Export file is unavailable")
        if is_within(path, EXPORT_DIR) or is_within(path, PREVIEW_DIR):
            thumb_dir = PROJECT_MEDIA_DIR / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = thumb_dir / f"export-{export_id}.jpg"
            if extract_thumbnail(path, thumb_path, at=0.5, width=640):
                if project:
                    with get_db() as db:
                        db.execute(
                            "UPDATE projects SET thumbnail_path = ? WHERE id = ?",
                            (relative_to_media(thumb_path), project["id"]),
                        )
                return FileResponse(thumb_path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="No thumbnail is available for this export")


@router.post("/{export_id}/cancel")
def cancel_export(export_id: str) -> dict:
    row = get_export(export_id)
    if not row:
        raise HTTPException(status_code=404, detail="Export not found")
    if row["status"] not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="This export is not running")
    request_cancel(export_id)
    return {"cancelled": True, "message": "Cancellation requested. The renderer will stop shortly."}


@router.delete("/{export_id}")
def delete_export(export_id: str) -> dict:
    row = get_export(export_id)
    if not row:
        raise HTTPException(status_code=404, detail="Export not found")
    if row["status"] == "running":
        raise HTTPException(status_code=409, detail="Cancel the render before deleting it")
    if row.get("output_path"):
        try:
            path = media_path(row["output_path"])
            if (is_within(path, EXPORT_DIR) or is_within(path, PREVIEW_DIR)) and path.exists():
                path.unlink()
        except ValueError:
            pass
    with get_db() as db:
        db.execute("DELETE FROM exports WHERE id = ?", (export_id,))
    return {"deleted": True}
