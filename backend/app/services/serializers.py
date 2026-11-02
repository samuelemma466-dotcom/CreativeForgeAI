from __future__ import annotations

import json
from typing import Any


def json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, type(default)) else default
    except (TypeError, json.JSONDecodeError):
        return default


def brand_out(row: dict[str, Any]) -> dict[str, Any]:
    colors = json_value(row.get("colors"), [])
    socials = json_value(row.get("socials"), {})
    platforms = json_value(row.get("platforms"), [])
    contact = json_value(row.get("contact"), {})
    if isinstance(contact, str):
        contact = {"details": contact} if contact else {}
    logo_id = row.get("logo_media_id")
    return {
        **row,
        "description": row.get("description") or "",
        "business_description": row.get("description") or "",
        "products": row.get("products") or "",
        "products_and_services": row.get("products") or "",
        "audience": row.get("audience") or "",
        "target_audience": row.get("audience") or "",
        "voice": row.get("voice") or "",
        "brand_voice": row.get("voice") or "",
        "guidelines": row.get("guidelines") or "",
        "brand_guidelines": row.get("guidelines") or "",
        "colors": colors,
        "contact": contact,
        "socials": socials,
        "social_links": socials,
        "platforms": platforms,
        "preferred_platforms": platforms,
        "logo_media_id": logo_id,
        "logo_url": f"/api/media/{logo_id}/content" if logo_id else None,
    }


def campaign_out(row: dict[str, Any], brand_name: str | None = None, copy_count: int = 0) -> dict[str, Any]:
    return {
        **row,
        "strategy": json_value(row.get("strategy"), {}),
        "brand_name": brand_name,
        "copy_count": copy_count,
    }


def project_out(
    row: dict[str, Any],
    brand_name: str | None = None,
    include_data: bool = False,
) -> dict[str, Any]:
    output = {
        "id": row["id"],
        "type": row["type"],
        "name": row["name"],
        "description": row.get("description") or "",
        "status": row.get("status") or "draft",
        "brand_id": row.get("brand_id"),
        "brand_name": brand_name,
        "campaign_id": row.get("campaign_id"),
        "thumbnail_url": (
            f"/api/projects/{row['id']}/thumbnail"
            if row.get("thumbnail_path")
            else None
        ),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_data:
        output["data"] = json_value(row.get("data"), {})
    return output


def media_out(row: dict[str, Any]) -> dict[str, Any]:
    media_id = row["id"]
    return {
        "id": media_id,
        "original_name": row["original_name"],
        "mime_type": row["mime_type"],
        "content_type": row["mime_type"],
        "kind": row["kind"],
        "size_bytes": row["size_bytes"],
        "width": row.get("width"),
        "height": row.get("height"),
        "duration": row.get("duration"),
        "created_at": row["created_at"],
        "url": f"/api/media/{media_id}/content",
        "content_url": f"/api/media/{media_id}/content",
    }


def export_out(row: dict[str, Any]) -> dict[str, Any]:
    status = row["status"]
    paths = json_value(row.get("settings"), {})
    probe = json_value(row.get("probe"), {})
    return {
        "id": row["id"],
        "project_id": row.get("project_id"),
        "type": row["type"],
        "format": row["format"],
        "status": status,
        "progress": row.get("progress") or 0,
        "error": row.get("error"),
        "settings": paths,
        "probe": probe,
        "created_at": row["created_at"],
        "completed_at": row.get("completed_at"),
        "file_url": f"/api/exports/{row['id']}/file" if status == "completed" else None,
        "thumbnail_url": f"/api/exports/{row['id']}/thumbnail" if status == "completed" else None,
    }


def subtitle_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "style": json_value(row.get("style"), {}),
        "download_url": f"/api/subtitles/{row['id']}/download",
    }


def copy_out(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)
