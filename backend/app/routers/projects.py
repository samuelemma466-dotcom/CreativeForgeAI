from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..db import get_db, utc_now
from ..schemas import DesignData, ProjectUpdate, VideoData
from ..services.serializers import project_out
from .helpers import (
    get_brand,
    get_campaign,
    get_project,
    parse_json_field,
    project_brand_name,
    thumbnail_file,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _validate_links(brand_id: str | None, campaign_id: str | None) -> None:
    if brand_id:
        get_brand(brand_id)
    if campaign_id:
        get_campaign(campaign_id)


def _validate_project_data(project_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if project_type == "design":
        return DesignData.model_validate(data).model_dump()
    if project_type == "video":
        return VideoData.model_validate(data).model_dump()
    return data


@router.get("")
def list_projects(
    type: str | None = None,
    brand_id: str | None = None,
    campaign_id: str | None = None,
    limit: int = 200,
) -> dict:
    if type and type not in {"design", "video", "general"}:
        raise HTTPException(status_code=422, detail="Invalid project type")
    clauses: list[str] = []
    params: list[Any] = []
    if type:
        clauses.append("p.type = ?")
        params.append(type)
    if brand_id:
        clauses.append("p.brand_id = ?")
        params.append(brand_id)
    if campaign_id:
        clauses.append("p.campaign_id = ?")
        params.append(campaign_id)
    query = """
        SELECT p.*, b.name AS brand_name FROM projects p
        LEFT JOIN brands b ON b.id = p.brand_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY p.updated_at DESC LIMIT ?"
    params.append(max(1, min(limit, 500)))
    with get_db() as db:
        rows = db.execute(query, params).fetchall()
    return {
        "projects": [
            project_out(dict(row), row["brand_name"], include_data=False) for row in rows
        ]
    }


@router.post("", status_code=201)
def create_project(payload: dict) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Project name is required")
    project_type = payload.get("type") or "general"
    if project_type not in {"design", "video", "general"}:
        raise HTTPException(status_code=422, detail="Invalid project type")
    brand_id = payload.get("brand_id") or None
    campaign_id = payload.get("campaign_id") or None
    _validate_links(brand_id, campaign_id)
    now = utc_now()
    project_id = uuid4().hex
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    data = _validate_project_data(project_type, data)
    with get_db() as db:
        db.execute(
            """
            INSERT INTO projects
                (id, type, name, description, status, brand_id, campaign_id, data,
                 thumbnail_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                project_id,
                project_type,
                name[:200],
                str(payload.get("description") or "")[:4000],
                payload.get("status") if payload.get("status") in {"draft", "active", "archived"} else "draft",
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
def read_project(project_id: str) -> dict:
    row = get_project(project_id)
    return project_out(row, project_brand_name(row), include_data=True)


@router.put("/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate) -> dict:
    existing = get_project(project_id)
    name = payload.name if payload.name is not None else existing["name"]
    description = payload.description if payload.description is not None else existing.get("description", "")
    status = payload.status if payload.status is not None else existing.get("status", "draft")
    brand_id = payload.brand_id if "brand_id" in payload.model_fields_set else existing.get("brand_id")
    campaign_id = (
        payload.campaign_id
        if "campaign_id" in payload.model_fields_set
        else existing.get("campaign_id")
    )
    _validate_links(brand_id, campaign_id)
    if payload.data is not None:
        data = _validate_project_data(existing["type"], payload.data)
    else:
        data = parse_json_field(existing.get("data"), {})
    with get_db() as db:
        db.execute(
            """
            UPDATE projects SET name = ?, description = ?, status = ?, brand_id = ?,
                campaign_id = ?, data = ?, updated_at = ? WHERE id = ?
            """,
            (
                name,
                description,
                status,
                brand_id,
                campaign_id,
                json.dumps(data),
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
def delete_project(project_id: str) -> dict:
    get_project(project_id)
    with get_db() as db:
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return {"deleted": True}


@router.get("/{project_id}/thumbnail")
def project_thumbnail(project_id: str) -> FileResponse:
    row = get_project(project_id)
    path = thumbnail_file(row)
    return FileResponse(path, media_type="image/jpeg", filename=path.name)
