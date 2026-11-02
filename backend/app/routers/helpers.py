from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from ..db import get_db
from ..utils.security import media_path
from pathlib import Path

BRAND_ALIASES = {
    "business_description": "description",
    "products_and_services": "products",
    "target_audience": "audience",
    "brand_voice": "voice",
    "social_links": "socials",
    "preferred_platforms": "platforms",
    "brand_guidelines": "guidelines",
}

BRAND_FIELDS = [
    "name",
    "description",
    "industry",
    "products",
    "audience",
    "voice",
    "colors",
    "logo_media_id",
    "contact",
    "website",
    "socials",
    "platforms",
    "guidelines",
]


def normalize_brand_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    for alias, canonical in BRAND_ALIASES.items():
        if alias in normalized and canonical not in normalized:
            normalized[canonical] = normalized[alias]
        normalized.pop(alias, None)
    if isinstance(normalized.get("contact"), str):
        value = normalized["contact"].strip()
        normalized["contact"] = {"details": value} if value else {}
    return {key: value for key, value in normalized.items() if key in BRAND_FIELDS}


def brand_canonical_dict(row: dict[str, Any]) -> dict[str, Any]:
    def parsed(value: Any, default: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value) if value else default
        except (TypeError, json.JSONDecodeError):
            return default

    return {
        "name": row["name"],
        "description": row.get("description") or "",
        "industry": row.get("industry") or "",
        "products": row.get("products") or "",
        "audience": row.get("audience") or "",
        "voice": row.get("voice") or "",
        "colors": parsed(row.get("colors"), []),
        "logo_media_id": row.get("logo_media_id"),
        "contact": parsed(row.get("contact"), {}),
        "website": row.get("website") or "",
        "socials": parsed(row.get("socials"), {}),
        "platforms": parsed(row.get("platforms"), []),
        "guidelines": row.get("guidelines") or "",
    }


def get_brand(brand_id: str) -> dict[str, Any]:
    with get_db() as db:
        row = db.execute("SELECT * FROM brands WHERE id = ?", (brand_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Brand not found")
    return dict(row)


def get_campaign(campaign_id: str) -> dict[str, Any]:
    with get_db() as db:
        row = db.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return dict(row)


def get_project(project_id: str, project_type: str | None = None) -> dict[str, Any]:
    with get_db() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    if project_type and row["type"] != project_type:
        raise HTTPException(status_code=404, detail=f"{project_type.title()} project not found")
    return dict(row)


def project_brand_name(row: dict[str, Any]) -> str | None:
    if not row.get("brand_id"):
        return None
    with get_db() as db:
        brand = db.execute("SELECT name FROM brands WHERE id = ?", (row["brand_id"],)).fetchone()
    return brand["name"] if brand else None


def require_media(media_id: str, kind: str | None = None) -> dict[str, Any]:
    with get_db() as db:
        row = db.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Referenced media asset does not exist")
    if kind and row["kind"] != kind:
        raise HTTPException(status_code=400, detail=f"Referenced media is not {kind}")
    return dict(row)


def thumbnail_file(row: dict[str, Any]) -> Path:
    if not row.get("thumbnail_path"):
        raise HTTPException(status_code=404, detail="No thumbnail has been generated yet")
    try:
        path = media_path(row["thumbnail_path"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Thumbnail is unavailable") from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file is missing")
    return path


def parse_json_field(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "null")
        return parsed if parsed is not None else default
    except (TypeError, json.JSONDecodeError):
        return default
