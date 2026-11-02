from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from PIL import Image

from ..config import EXPORT_DIR, PROJECT_MEDIA_DIR
from ..db import get_db, utc_now
from ..schemas import DesignData, DesignExportRequest
from ..services.design_render import TEMPLATES, DesignRenderError, render_design, template_data
from ..services.serializers import export_out, project_out
from ..utils.security import relative_to_media
from .helpers import (
    get_brand,
    get_campaign,
    get_project,
    parse_json_field,
    project_brand_name,
)

router = APIRouter(prefix="/api/design", tags=["design"])


@router.get("/templates")
def list_templates() -> dict:
    return {"templates": TEMPLATES}


@router.get("")
def list_design_projects(brand_id: str | None = None) -> dict:
    query = """
        SELECT p.*, b.name AS brand_name FROM projects p
        LEFT JOIN brands b ON b.id = p.brand_id WHERE p.type = 'design'
    """
    params: list[str] = []
    if brand_id:
        query += " AND p.brand_id = ?"
        params.append(brand_id)
    query += " ORDER BY p.updated_at DESC"
    with get_db() as db:
        rows = db.execute(query, params).fetchall()
    return {
        "projects": [
            project_out(dict(row), row["brand_name"], include_data=False) for row in rows
        ]
    }


@router.post("", status_code=201)
def create_design_project(payload: dict) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Project name is required")
    brand_id = payload.get("brand_id") or None
    campaign_id = payload.get("campaign_id") or None
    brand = get_brand(brand_id) if brand_id else None
    campaign = get_campaign(campaign_id) if campaign_id else None
    template_id = payload.get("template_id")
    try:
        if template_id:
            data = template_data(template_id, brand, campaign)
        else:
            width = int(payload.get("width") or 1080)
            height = int(payload.get("height") or 1080)
            data = DesignData(
                width=width,
                height=height,
                background="#111214",
                layers=[],
            ).model_dump()
    except (DesignRenderError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Ensure the template output is valid before persisting it.
    data = DesignData.model_validate(data).model_dump()
    project_id = uuid4().hex
    now = utc_now()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO projects
                (id, type, name, description, status, brand_id, campaign_id, data,
                 thumbnail_path, created_at, updated_at)
            VALUES (?, 'design', ?, ?, 'draft', ?, ?, ?, NULL, ?, ?)
            """,
            (
                project_id,
                name[:200],
                str(payload.get("description") or "")[:4000],
                brand_id,
                campaign_id,
                json.dumps(data),
                now,
                now,
            ),
        )
        row = db.execute(
            "SELECT p.*, b.name AS brand_name FROM projects p LEFT JOIN brands b ON b.id = p.brand_id WHERE p.id = ?",
            (project_id,),
        ).fetchone()
    return project_out(dict(row), row["brand_name"], include_data=True)


@router.get("/{project_id}")
def read_design_project(project_id: str) -> dict:
    row = get_project(project_id, "design")
    return project_out(row, project_brand_name(row), include_data=True)


@router.put("/{project_id}")
def update_design_project(project_id: str, payload: dict) -> dict:
    existing = get_project(project_id, "design")
    data = payload.get("data", parse_json_field(existing.get("data"), {}))
    try:
        validated = DesignData.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid design composition: {exc}") from exc
    name = str(payload.get("name") or existing["name"])[:200]
    brand_id = payload.get("brand_id", existing.get("brand_id"))
    campaign_id = payload.get("campaign_id", existing.get("campaign_id"))
    with get_db() as db:
        db.execute(
            """
            UPDATE projects SET name = ?, description = ?, status = ?, brand_id = ?,
                campaign_id = ?, data = ?, updated_at = ? WHERE id = ?
            """,
            (
                name,
                str(payload.get("description", existing.get("description") or ""))[:4000],
                payload.get("status", existing.get("status") or "draft"),
                brand_id,
                campaign_id,
                json.dumps(validated.model_dump()),
                utc_now(),
                project_id,
            ),
        )
        row = db.execute(
            "SELECT p.*, b.name AS brand_name FROM projects p LEFT JOIN brands b ON b.id = p.brand_id WHERE p.id = ?",
            (project_id,),
        ).fetchone()
    return project_out(dict(row), row["brand_name"], include_data=True)


@router.delete("/{project_id}")
def delete_design_project(project_id: str) -> dict:
    get_project(project_id, "design")
    with get_db() as db:
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return {"deleted": True}


@router.post("/{project_id}/export")
def export_design(project_id: str, payload: DesignExportRequest) -> dict:
    row = get_project(project_id, "design")
    data = parse_json_field(row.get("data"), {})
    output_name = f"{project_id[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}.{payload.format}"
    output_path = EXPORT_DIR / "design" / project_id / output_name
    try:
        width, height = render_design(data, output_path, payload.scale)
    except DesignRenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Design export failed: {exc}") from exc

    # Create a lightweight project thumbnail.
    try:
        thumb_dir = PROJECT_MEDIA_DIR / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"{project_id}.jpg"
        with Image.open(output_path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((640, 640), Image.Resampling.LANCZOS)
            thumb.save(thumb_path, "JPEG", quality=86)
        thumbnail_relative = relative_to_media(thumb_path)
    except Exception:
        thumbnail_relative = None

    export_id = uuid4().hex
    now = utc_now()
    relative_output = relative_to_media(output_path)
    with get_db() as db:
        db.execute(
            """
            INSERT INTO exports
                (id, project_id, type, format, status, progress, output_path, settings,
                 probe, error, created_at, completed_at)
            VALUES (?, ?, 'design', ?, 'completed', 100, ?, ?, ?, NULL, ?, ?)
            """,
            (
                export_id,
                project_id,
                payload.format,
                relative_output,
                json.dumps({"scale": payload.scale, "kind": "design"}),
                json.dumps({"width": width, "height": height, "valid": True}),
                now,
                now,
            ),
        )
        if thumbnail_relative:
            db.execute(
                "UPDATE projects SET thumbnail_path = ?, updated_at = ? WHERE id = ?",
                (thumbnail_relative, now, project_id),
            )
        export_row = db.execute("SELECT * FROM exports WHERE id = ?", (export_id,)).fetchone()
    output = export_out(dict(export_row))
    output["width"] = width
    output["height"] = height
    return output
