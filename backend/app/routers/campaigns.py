from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ..db import get_db, utc_now
from ..schemas import CampaignCreate, CampaignUpdate
from ..services.ai import generate_strategy
from ..services.providers import ProviderError
from ..services.serializers import campaign_out
from .helpers import get_brand, get_campaign

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

CAMPAIGN_FIELDS = [
    "name",
    "brand_id",
    "product",
    "audience",
    "objective",
    "platform",
    "duration",
    "budget",
    "offer",
    "problem",
    "cta",
    "instructions",
    "status",
]


@router.get("")
def list_campaigns(brand_id: str | None = None) -> dict:
    query = """
        SELECT c.*, b.name AS brand_name,
               (SELECT COUNT(*) FROM copy_items ci WHERE ci.campaign_id = c.id) AS copy_count
        FROM campaigns c LEFT JOIN brands b ON b.id = c.brand_id
    """
    params: list[str] = []
    if brand_id:
        query += " WHERE c.brand_id = ?"
        params.append(brand_id)
    query += " ORDER BY c.updated_at DESC"
    with get_db() as db:
        rows = db.execute(query, params).fetchall()
    return {
        "campaigns": [
            campaign_out(dict(row), row["brand_name"], row["copy_count"] or 0) for row in rows
        ]
    }


@router.post("", status_code=201)
def create_campaign(payload: dict) -> dict:
    campaign = CampaignCreate.model_validate(payload)
    if campaign.brand_id:
        get_brand(campaign.brand_id)
    campaign_id = uuid4().hex
    now = utc_now()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO campaigns
                (id, brand_id, name, product, audience, objective, platform, duration,
                 budget, offer, problem, cta, instructions, status, strategy,
                 generated_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', NULL, ?, ?)
            """,
            (
                campaign_id,
                campaign.brand_id,
                campaign.name,
                campaign.product,
                campaign.audience,
                campaign.objective,
                campaign.platform,
                campaign.duration,
                campaign.budget,
                campaign.offer,
                campaign.problem,
                campaign.cta,
                campaign.instructions,
                campaign.status,
                now,
                now,
            ),
        )
        row = db.execute(
            """
            SELECT c.*, b.name AS brand_name,
                   (SELECT COUNT(*) FROM copy_items ci WHERE ci.campaign_id = c.id) AS copy_count
            FROM campaigns c LEFT JOIN brands b ON b.id = c.brand_id WHERE c.id = ?
            """,
            (campaign_id,),
        ).fetchone()
    return campaign_out(dict(row), row["brand_name"], row["copy_count"] or 0)


@router.get("/{campaign_id}")
def read_campaign(campaign_id: str) -> dict:
    with get_db() as db:
        row = db.execute(
            """
            SELECT c.*, b.name AS brand_name,
                   (SELECT COUNT(*) FROM copy_items ci WHERE ci.campaign_id = c.id) AS copy_count
            FROM campaigns c LEFT JOIN brands b ON b.id = c.brand_id WHERE c.id = ?
            """,
            (campaign_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign_out(dict(row), row["brand_name"], row["copy_count"] or 0)


@router.put("/{campaign_id}")
def update_campaign(campaign_id: str, payload: dict) -> dict:
    existing = get_campaign(campaign_id)
    merged = {key: existing.get(key) for key in CAMPAIGN_FIELDS}
    merged.update({key: value for key, value in payload.items() if key in CAMPAIGN_FIELDS})
    campaign = CampaignUpdate.model_validate(merged)
    if campaign.brand_id:
        get_brand(campaign.brand_id)
    with get_db() as db:
        db.execute(
            """
            UPDATE campaigns SET
                brand_id = ?, name = ?, product = ?, audience = ?, objective = ?,
                platform = ?, duration = ?, budget = ?, offer = ?, problem = ?,
                cta = ?, instructions = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                campaign.brand_id,
                campaign.name,
                campaign.product,
                campaign.audience,
                campaign.objective,
                campaign.platform,
                campaign.duration,
                campaign.budget,
                campaign.offer,
                campaign.problem,
                campaign.cta,
                campaign.instructions,
                campaign.status,
                utc_now(),
                campaign_id,
            ),
        )
        row = db.execute(
            """
            SELECT c.*, b.name AS brand_name,
                   (SELECT COUNT(*) FROM copy_items ci WHERE ci.campaign_id = c.id) AS copy_count
            FROM campaigns c LEFT JOIN brands b ON b.id = c.brand_id WHERE c.id = ?
            """,
            (campaign_id,),
        ).fetchone()
    return campaign_out(dict(row), row["brand_name"], row["copy_count"] or 0)


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: str) -> dict:
    get_campaign(campaign_id)
    with get_db() as db:
        db.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
    return {"deleted": True}


@router.post("/{campaign_id}/generate")
async def generate_campaign_strategy(campaign_id: str) -> dict:
    campaign = get_campaign(campaign_id)
    brand = get_brand(campaign["brand_id"]) if campaign.get("brand_id") else None
    try:
        result = await generate_strategy(campaign, brand)
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    with get_db() as db:
        db.execute(
            "UPDATE campaigns SET strategy = ?, generated_at = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(result["strategy"]),
                utc_now(),
                utc_now(),
                campaign_id,
            ),
        )
        row = db.execute(
            """
            SELECT c.*, b.name AS brand_name,
                   (SELECT COUNT(*) FROM copy_items ci WHERE ci.campaign_id = c.id) AS copy_count
            FROM campaigns c LEFT JOIN brands b ON b.id = c.brand_id WHERE c.id = ?
            """,
            (campaign_id,),
        ).fetchone()
    output = campaign_out(dict(row), row["brand_name"], row["copy_count"] or 0)
    output["generation"] = {
        "provider": result["provider"],
        "model": result["model"],
        "duration_ms": result.get("duration_ms"),
        "prompt_tokens": result.get("prompt_tokens"),
        "completion_tokens": result.get("completion_tokens"),
        "generated_at": row["generated_at"],
    }
    return output
