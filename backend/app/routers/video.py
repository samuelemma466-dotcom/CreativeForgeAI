from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ..db import get_db, utc_now
from ..schemas import PreviewRequest, VideoCreate, VideoData, VideoExportRequest
from ..services.render_jobs import submit_render
from ..services.serializers import export_out, project_out
from .helpers import (
    get_brand,
    get_campaign,
    get_project,
    parse_json_field,
    project_brand_name,
    require_media,
)

router = APIRouter(prefix="/api", tags=["video"])

PRESETS = [
    {
        "id": "tiktok",
        "name": "TikTok",
        "platform": "TikTok",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "aspect": "9:16",
        "description": "Vertical short-form video, recommended 1080x1920.",
    },
    {
        "id": "instagram_reels",
        "name": "Instagram Reels",
        "platform": "Instagram",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "aspect": "9:16",
        "description": "Vertical Reels delivery, 1080x1920.",
    },
    {
        "id": "instagram_feed",
        "name": "Instagram Feed",
        "platform": "Instagram",
        "width": 1080,
        "height": 1350,
        "fps": 30,
        "aspect": "4:5",
        "description": "Portrait feed video, 1080x1350.",
    },
    {
        "id": "facebook_feed",
        "name": "Facebook Feed",
        "platform": "Facebook",
        "width": 1080,
        "height": 1080,
        "fps": 30,
        "aspect": "1:1",
        "description": "Square feed video, 1080x1080.",
    },
    {
        "id": "facebook_stories",
        "name": "Facebook Stories",
        "platform": "Facebook",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "aspect": "9:16",
        "description": "Vertical Stories delivery, 1080x1920.",
    },
    {
        "id": "youtube_shorts",
        "name": "YouTube Shorts",
        "platform": "YouTube",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "aspect": "9:16",
        "description": "Vertical Shorts delivery, 1080x1920.",
    },
    {
        "id": "youtube_landscape",
        "name": "YouTube Landscape",
        "platform": "YouTube",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "aspect": "16:9",
        "description": "Full HD landscape delivery, 1920x1080.",
    },
    {
        "id": "general_landscape",
        "name": "General Landscape",
        "platform": "General",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "aspect": "16:9",
        "description": "General purpose 16:9 MP4.",
    },
]

ASPECT_DIMENSIONS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


@router.get("/presets")
def list_presets() -> dict:
    return {"presets": PRESETS}


def _default_tracks() -> list[dict]:
    return [
        {"id": uuid4().hex, "type": "visual", "name": "Visuals", "clips": []},
        {"id": uuid4().hex, "type": "text", "name": "Text & titles", "clips": []},
        {"id": uuid4().hex, "type": "audio", "name": "Voice & music", "clips": []},
    ]


def _validate_media(data: VideoData) -> None:
    for track in data.tracks:
        for clip in track.clips:
            if not clip.media_id:
                continue
            media = require_media(clip.media_id)
            if clip.kind in {"image"} and media["kind"] != "image":
                raise HTTPException(
                    status_code=422,
                    detail=f"Clip '{clip.label or clip.id}' needs an image asset",
                )
            if clip.kind == "video" and media["kind"] != "video":
                raise HTTPException(
                    status_code=422,
                    detail=f"Clip '{clip.label or clip.id}' needs a video asset",
                )
            if clip.kind in {"audio", "voice", "music"} and media["kind"] != "audio":
                raise HTTPException(
                    status_code=422,
                    detail=f"Clip '{clip.label or clip.id}' needs an audio asset",
                )


@router.get("/video")
def list_video_projects(brand_id: str | None = None) -> dict:
    query = """
        SELECT p.*, b.name AS brand_name FROM projects p
        LEFT JOIN brands b ON b.id = p.brand_id WHERE p.type = 'video'
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


@router.post("/video", status_code=201)
def create_video_project(payload: dict) -> dict:
    request = VideoCreate.model_validate(payload)
    if request.brand_id:
        get_brand(request.brand_id)
    if request.campaign_id:
        get_campaign(request.campaign_id)
    if request.width and request.height:
        width, height = request.width, request.height
    else:
        width, height = ASPECT_DIMENSIONS[request.aspect_ratio]
    data = VideoData(
        width=width,
        height=height,
        fps=request.fps,
        tracks=_default_tracks(),
    )
    project_id = uuid4().hex
    now = utc_now()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO projects
                (id, type, name, description, status, brand_id, campaign_id, data,
                 thumbnail_path, created_at, updated_at)
            VALUES (?, 'video', ?, '', 'draft', ?, ?, ?, NULL, ?, ?)
            """,
            (
                project_id,
                request.name[:200],
                request.brand_id,
                request.campaign_id,
                json.dumps(data.model_dump()),
                now,
                now,
            ),
        )
        row = db.execute(
            "SELECT p.*, b.name AS brand_name FROM projects p LEFT JOIN brands b ON b.id = p.brand_id WHERE p.id = ?",
            (project_id,),
        ).fetchone()
    return project_out(dict(row), row["brand_name"], include_data=True)


@router.get("/video/{project_id}")
def read_video_project(project_id: str) -> dict:
    row = get_project(project_id, "video")
    return project_out(row, project_brand_name(row), include_data=True)


@router.put("/video/{project_id}")
def update_video_project(project_id: str, payload: dict) -> dict:
    existing = get_project(project_id, "video")
    raw_data = payload.get("data", parse_json_field(existing.get("data"), {}))
    try:
        data = VideoData.model_validate(raw_data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid video timeline: {exc}") from exc
    _validate_media(data)
    name = str(payload.get("name") or existing["name"])[:200]
    brand_id = payload.get("brand_id", existing.get("brand_id"))
    campaign_id = payload.get("campaign_id", existing.get("campaign_id"))
    if brand_id:
        get_brand(brand_id)
    if campaign_id:
        get_campaign(campaign_id)
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
                json.dumps(data.model_dump()),
                utc_now(),
                project_id,
            ),
        )
        row = db.execute(
            "SELECT p.*, b.name AS brand_name FROM projects p LEFT JOIN brands b ON b.id = p.brand_id WHERE p.id = ?",
            (project_id,),
        ).fetchone()
    return project_out(dict(row), row["brand_name"], include_data=True)


@router.delete("/video/{project_id}")
def delete_video_project(project_id: str) -> dict:
    get_project(project_id, "video")
    with get_db() as db:
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return {"deleted": True}


def _create_render_job(project: dict, mode: str, settings: dict) -> dict:
    data = parse_json_field(project.get("data"), {})
    try:
        parsed = VideoData.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Timeline is invalid: {exc}") from exc
    if parsed.duration() <= 0.1:
        raise HTTPException(status_code=422, detail="The timeline is empty. Add a clip first.")
    export_id = uuid4().hex
    now = utc_now()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO exports
                (id, project_id, type, format, status, progress, output_path, settings,
                 probe, error, created_at, completed_at)
            VALUES (?, ?, ?, 'mp4', 'queued', 0, NULL, ?, '{}', NULL, ?, NULL)
            """,
            (
                export_id,
                project["id"],
                mode,
                json.dumps({"mode": mode, **settings}),
                now,
            ),
        )
        row = db.execute("SELECT * FROM exports WHERE id = ?", (export_id,)).fetchone()
    submit_render(export_id)
    return export_out(dict(row))


@router.post("/video/{project_id}/preview")
def preview_video(project_id: str, payload: PreviewRequest) -> dict:
    project = get_project(project_id, "video")
    return _create_render_job(project, "preview", {"max_width": payload.max_width})


@router.post("/video/{project_id}/export")
def export_video(project_id: str, payload: VideoExportRequest) -> dict:
    project = get_project(project_id, "video")
    preset = next((item for item in PRESETS if item["id"] == payload.preset), None)
    if not preset:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown export preset. Choose one of: {', '.join(item['id'] for item in PRESETS)}",
        )
    width = payload.width or preset["width"]
    height = payload.height or preset["height"]
    fps = payload.fps or preset["fps"]
    return _create_render_job(
        project,
        "video",
        {
            "width": width,
            "height": height,
            "fps": fps,
            "crf": payload.crf,
            "preset": preset["id"],
            "preset_name": preset["name"],
        },
    )
