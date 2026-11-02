from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response

from ..db import get_db, utc_now
from ..schemas import SubtitleCreate, SubtitleUpdate
from ..services.serializers import subtitle_out
from ..services.subtitles import SrtError, normalize_srt, validate_srt
from .helpers import get_project, parse_json_field

router = APIRouter(prefix="/api/subtitles", tags=["subtitles"])


def _get_subtitle(subtitle_id: str) -> dict:
    with get_db() as db:
        row = db.execute("SELECT * FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Subtitle document not found")
    return dict(row)


def _associate(project_id: str | None, subtitle_id: str | None) -> None:
    if not project_id:
        return
    project = get_project(project_id, "video")
    data = parse_json_field(project.get("data"), {})
    if subtitle_id:
        data["subtitle_id"] = subtitle_id
    else:
        data.pop("subtitle_id", None)
    with get_db() as db:
        db.execute(
            "UPDATE projects SET data = ?, updated_at = ? WHERE id = ?",
            (json.dumps(data), utc_now(), project_id),
        )


def _clear_assocation(project_id: str | None, subtitle_id: str) -> None:
    if not project_id:
        return
    with get_db() as db:
        row = db.execute("SELECT data FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        return
    data = parse_json_field(row["data"], {})
    if data.get("subtitle_id") == subtitle_id:
        data.pop("subtitle_id", None)
        with get_db() as db:
            db.execute(
                "UPDATE projects SET data = ?, updated_at = ? WHERE id = ?",
                (json.dumps(data), utc_now(), project_id),
            )


@router.get("")
def list_subtitles(project_id: str | None = None) -> dict:
    if project_id:
        with get_db() as db:
            rows = db.execute(
                "SELECT * FROM subtitles WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
    else:
        with get_db() as db:
            rows = db.execute("SELECT * FROM subtitles ORDER BY updated_at DESC").fetchall()
    return {"subtitles": [subtitle_out(dict(row)) for row in rows]}


@router.post("", status_code=201)
def create_subtitle(payload: SubtitleCreate) -> dict:
    if payload.project_id:
        get_project(payload.project_id, "video")
    try:
        normalized = normalize_srt(payload.srt)
    except SrtError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    subtitle_id = uuid4().hex
    now = utc_now()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO subtitles (id, project_id, title, srt, style, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subtitle_id,
                payload.project_id,
                payload.title[:200],
                normalized,
                json.dumps(payload.style),
                now,
                now,
            ),
        )
        row = db.execute("SELECT * FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()
    if payload.project_id:
        _associate(payload.project_id, subtitle_id)
    return subtitle_out(dict(row))


@router.get("/{subtitle_id}")
def read_subtitle(subtitle_id: str) -> dict:
    return subtitle_out(_get_subtitle(subtitle_id))


@router.put("/{subtitle_id}")
def update_subtitle(subtitle_id: str, payload: SubtitleUpdate) -> dict:
    existing = _get_subtitle(subtitle_id)
    new_project_id = payload.project_id if payload.project_id is not None else existing.get("project_id")
    if new_project_id:
        get_project(new_project_id, "video")
    try:
        normalized = normalize_srt(payload.srt)
    except SrtError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with get_db() as db:
        db.execute(
            """
            UPDATE subtitles SET project_id = ?, title = ?, srt = ?, style = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                new_project_id,
                payload.title[:200],
                normalized,
                json.dumps(payload.style),
                utc_now(),
                subtitle_id,
            ),
        )
        row = db.execute("SELECT * FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()
    if existing.get("project_id") and existing["project_id"] != new_project_id:
        _clear_assocation(existing["project_id"], subtitle_id)
    if new_project_id:
        _associate(new_project_id, subtitle_id)
    return subtitle_out(dict(row))


@router.delete("/{subtitle_id}")
def delete_subtitle(subtitle_id: str) -> dict:
    existing = _get_subtitle(subtitle_id)
    if existing.get("project_id"):
        _clear_assocation(existing["project_id"], subtitle_id)
    with get_db() as db:
        db.execute("DELETE FROM subtitles WHERE id = ?", (subtitle_id,))
    return {"deleted": True}


@router.post("/validate")
def validate_subtitles(payload: dict) -> dict:
    srt = payload.get("srt", "")
    if not isinstance(srt, str):
        raise HTTPException(status_code=422, detail="SRT content must be text")
    try:
        return validate_srt(srt)
    except SrtError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{subtitle_id}/download")
def download_subtitle(subtitle_id: str) -> Response:
    subtitle = _get_subtitle(subtitle_id)
    filename = "".join(c if c.isalnum() or c in "-_ " else "_" for c in subtitle["title"])[:80]
    return Response(
        content=subtitle["srt"],
        media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="{filename or "subtitles"}.srt"'},
    )
