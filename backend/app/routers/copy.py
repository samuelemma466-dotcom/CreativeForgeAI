from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ..db import get_db, utc_now
from ..schemas import COPY_KINDS, COPY_TONES, CopyGenerateRequest, CopyItemCreate
from ..services.ai import generate_copy
from ..services.providers import ProviderError
from ..services.serializers import copy_out
from .helpers import get_brand, get_campaign

router = APIRouter(prefix="/api/copy", tags=["copy"])


def _get_copy_item(copy_id: str) -> dict:
    with get_db() as db:
        row = db.execute("SELECT * FROM copy_items WHERE id = ?", (copy_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Copy item not found")
    return dict(row)


@router.get("")
def list_copy(campaign_id: str | None = None, brand_id: str | None = None) -> dict:
    query = """
        SELECT ci.*, c.name AS campaign_name, b.name AS brand_name
        FROM copy_items ci
        LEFT JOIN campaigns c ON c.id = ci.campaign_id
        LEFT JOIN brands b ON b.id = ci.brand_id
    """
    clauses: list[str] = []
    params: list[str] = []
    if campaign_id:
        clauses.append("ci.campaign_id = ?")
        params.append(campaign_id)
    if brand_id:
        clauses.append("ci.brand_id = ?")
        params.append(brand_id)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY ci.updated_at DESC"
    with get_db() as db:
        rows = db.execute(query, params).fetchall()
    return {"copies": [copy_out(dict(row)) for row in rows]}


@router.post("/generate")
async def generate_copy_endpoint(payload: CopyGenerateRequest) -> dict:
    campaign = None
    brand = None
    if payload.campaign_id:
        campaign = get_campaign(payload.campaign_id)
        if campaign.get("brand_id"):
            brand = get_brand(campaign["brand_id"])
    if payload.brand_id:
        brand = get_brand(payload.brand_id)
    try:
        result = await generate_copy(payload, campaign, brand)
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return result


@router.post("", status_code=201)
def save_copy(payload: CopyItemCreate) -> dict:
    if payload.kind not in COPY_KINDS:
        raise HTTPException(status_code=422, detail=f"Unsupported copy kind: {payload.kind}")
    if payload.tone and payload.tone not in COPY_TONES:
        raise HTTPException(status_code=422, detail=f"Unsupported tone: {payload.tone}")
    if payload.campaign_id:
        get_campaign(payload.campaign_id)
    if payload.brand_id:
        get_brand(payload.brand_id)
    copy_id = uuid4().hex
    now = utc_now()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO copy_items
                (id, campaign_id, brand_id, kind, tone, title, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                copy_id,
                payload.campaign_id,
                payload.brand_id,
                payload.kind,
                payload.tone,
                payload.title,
                payload.content,
                now,
                now,
            ),
        )
        row = db.execute("SELECT * FROM copy_items WHERE id = ?", (copy_id,)).fetchone()
    return copy_out(dict(row))


@router.put("/{copy_id}")
def update_copy(copy_id: str, payload: dict) -> dict:
    existing = _get_copy_item(copy_id)
    merged = {**existing}
    for key in ("campaign_id", "brand_id", "kind", "tone", "title", "content"):
        if key in payload:
            merged[key] = payload[key]
    item = CopyItemCreate.model_validate(merged)
    if item.kind not in COPY_KINDS:
        raise HTTPException(status_code=422, detail=f"Unsupported copy kind: {item.kind}")
    if item.tone and item.tone not in COPY_TONES:
        raise HTTPException(status_code=422, detail=f"Unsupported tone: {item.tone}")
    with get_db() as db:
        db.execute(
            """
            UPDATE copy_items SET campaign_id = ?, brand_id = ?, kind = ?, tone = ?,
                title = ?, content = ?, updated_at = ? WHERE id = ?
            """,
            (
                item.campaign_id,
                item.brand_id,
                item.kind,
                item.tone,
                item.title,
                item.content,
                utc_now(),
                copy_id,
            ),
        )
        row = db.execute("SELECT * FROM copy_items WHERE id = ?", (copy_id,)).fetchone()
    return copy_out(dict(row))


@router.delete("/{copy_id}")
def delete_copy(copy_id: str) -> dict:
    _get_copy_item(copy_id)
    with get_db() as db:
        db.execute("DELETE FROM copy_items WHERE id = ?", (copy_id,))
    return {"deleted": True}
