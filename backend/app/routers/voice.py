from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import VoiceRequest
from ..services.media import MediaValidationError
from ..services.serializers import media_out
from ..services.tts import generate_voice, list_voices

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.get("/voices")
def voices() -> dict:
    try:
        items = list_voices()
    except MediaValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"voices": items, "count": len(items)}


@router.post("/generate", status_code=201)
def create_voiceover(payload: VoiceRequest) -> dict:
    try:
        media = generate_voice(payload)
    except MediaValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return media_out(media)
