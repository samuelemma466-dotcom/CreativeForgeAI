from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ..db import get_db, utc_now
from ..schemas import BrandCreate
from ..services.serializers import brand_out
from .helpers import (
    brand_canonical_dict,
    get_brand,
    normalize_brand_payload,
    require_media,
)

router = APIRouter(prefix="/api/brands", tags=["brands"])


def _validate_logo(logo_media_id: str | None) -> None:
    if logo_media_id:
        require_media(logo_media_id, "image")


@router.get("")
def list_brands() -> dict:
    with get_db() as db:
        rows = db.execute("SELECT * FROM brands ORDER BY updated_at DESC").fetchall()
    return {"brands": [brand_out(dict(row)) for row in rows]}


@router.post("", status_code=201)
def create_brand(payload: dict) -> dict:
    normalized = normalize_brand_payload(payload)
    brand = BrandCreate.model_validate(normalized)
    _validate_logo(brand.logo_media_id)
    brand_id = uuid4().hex
    now = utc_now()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO brands
                (id, name, description, industry, products, audience, voice, colors,
                 logo_media_id, contact, website, socials, platforms, guidelines,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                brand_id,
                brand.name,
                brand.description,
                brand.industry,
                brand.products,
                brand.audience,
                brand.voice,
                json.dumps(brand.colors),
                brand.logo_media_id,
                json.dumps(brand.contact),
                brand.website,
                json.dumps(brand.socials),
                json.dumps(brand.platforms),
                brand.guidelines,
                now,
                now,
            ),
        )
        row = db.execute("SELECT * FROM brands WHERE id = ?", (brand_id,)).fetchone()
    return brand_out(dict(row))


@router.get("/{brand_id}")
def read_brand(brand_id: str) -> dict:
    return brand_out(get_brand(brand_id))


@router.put("/{brand_id}")
def update_brand(brand_id: str, payload: dict) -> dict:
    existing = get_brand(brand_id)
    merged = {**brand_canonical_dict(existing), **normalize_brand_payload(payload)}
    brand = BrandCreate.model_validate(merged)
    _validate_logo(brand.logo_media_id)
    with get_db() as db:
        db.execute(
            """
            UPDATE brands SET
                name = ?, description = ?, industry = ?, products = ?, audience = ?,
                voice = ?, colors = ?, logo_media_id = ?, contact = ?, website = ?,
                socials = ?, platforms = ?, guidelines = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                brand.name,
                brand.description,
                brand.industry,
                brand.products,
                brand.audience,
                brand.voice,
                json.dumps(brand.colors),
                brand.logo_media_id,
                json.dumps(brand.contact),
                brand.website,
                json.dumps(brand.socials),
                json.dumps(brand.platforms),
                brand.guidelines,
                utc_now(),
                brand_id,
            ),
        )
        row = db.execute("SELECT * FROM brands WHERE id = ?", (brand_id,)).fetchone()
    return brand_out(dict(row))


@router.delete("/{brand_id}")
def delete_brand(brand_id: str) -> dict:
    get_brand(brand_id)
    with get_db() as db:
        db.execute("DELETE FROM brands WHERE id = ?", (brand_id,))
    return {"deleted": True}
