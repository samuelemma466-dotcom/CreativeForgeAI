from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from ..db import get_db, setting_get, setting_set
from ..services.providers import (
    CLOUD_PROVIDER_IDS,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    PROVIDER_IDS,
    ProviderError,
    all_providers_status,
    build_provider_chain,
    generate_text,
    gemini_free_models,
    gemini_known_models,
    gemini_status,
    gemini_test,
    get_provider_settings,
    groq_free_models,
    groq_known_models,
    groq_status,
    groq_test,
    is_free_gemini_model,
    is_free_groq_model,
    ollama_test,
    openrouter_free_models,
    openrouter_status,
    openrouter_test,
    provider_chain_status,
    update_provider_settings,
)

router = APIRouter(prefix="/api", tags=["settings", "providers"])

LOCAL_OLLAMA_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _settings_payload() -> dict:
    values = get_provider_settings()
    with get_db() as db:
        theme = setting_get(db, "theme", "dark") or "dark"
    return {
        "ollama_url": values["ollama_url"],
        "ollama_model": values["ollama_model"],
        "openrouter_model": values["openrouter_model"],
        "openrouter_configured": values["openrouter_key_configured"],
        "gemini_model": values["gemini_model"],
        "gemini_configured": values["gemini_key_configured"],
        "groq_model": values["groq_model"],
        "groq_configured": values["groq_key_configured"],
        "ai_provider": values["ai_provider"],
        "provider_priority": values["provider_priority"],
        "auto_fallback": values["auto_fallback"],
        "free_only": True,
        "theme": theme if theme in {"dark", "light"} else "dark",
    }


def _models_unavailable(
    known: list[dict[str, Any]], exc: ProviderError, configured: bool
) -> dict[str, Any]:
    if not configured:
        return {
            "models": known,
            "free_only": True,
            "verified": False,
            "note": str(exc),
        }
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/settings")
def read_settings() -> dict:
    return _settings_payload()


@router.put("/settings")
def save_settings(payload: dict) -> dict:
    if payload.get("free_only") is False:
        raise HTTPException(status_code=400, detail="FREE_ONLY mode cannot be disabled")

    ollama_url = payload.get("ollama_url")
    if ollama_url is not None:
        if not isinstance(ollama_url, str):
            raise HTTPException(status_code=422, detail="Ollama URL must be a string")
        parsed = urlparse(ollama_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=422, detail="Ollama URL must be a valid http(s) URL")
        if parsed.hostname not in LOCAL_OLLAMA_HOSTS:
            raise HTTPException(
                status_code=422,
                detail="Ollama must run on localhost. Cloud Ollama hosts are not allowed in FREE_ONLY mode.",
            )

    ollama_model = payload.get("ollama_model")
    if ollama_model is not None and (not isinstance(ollama_model, str) or not ollama_model.strip()):
        raise HTTPException(status_code=422, detail="Ollama model cannot be empty")

    openrouter_model = payload.get("openrouter_model")
    if openrouter_model is not None:
        if not isinstance(openrouter_model, str):
            raise HTTPException(status_code=422, detail="OpenRouter model must be a string")
        if openrouter_model and not openrouter_model.endswith(":free"):
            raise HTTPException(
                status_code=400,
                detail="Paid model rejected. Only OpenRouter models ending in ':free' are allowed.",
            )

    gemini_model = payload.get("gemini_model")
    if gemini_model is not None:
        if not isinstance(gemini_model, str):
            raise HTTPException(status_code=422, detail="Gemini model must be a string")
        gemini_model = gemini_model.strip() or DEFAULT_GEMINI_MODEL
        if not is_free_gemini_model(gemini_model):
            raise HTTPException(
                status_code=400,
                detail="Paid or non-text Gemini model rejected. Only free-tier Flash, Flash-Lite and Pro text models are allowed.",
            )

    groq_model = payload.get("groq_model")
    if groq_model is not None:
        if not isinstance(groq_model, str):
            raise HTTPException(status_code=422, detail="Groq model must be a string")
        groq_model = groq_model.strip() or DEFAULT_GROQ_MODEL
        if not is_free_groq_model(groq_model):
            raise HTTPException(
                status_code=400,
                detail="Paid or non-text Groq model rejected. Only models on Groq's Free Plan Limits table are allowed.",
            )

    ai_provider = payload.get("ai_provider")
    if ai_provider is not None and ai_provider not in PROVIDER_IDS:
        raise HTTPException(status_code=422, detail="Unsupported AI provider")

    provider_priority = payload.get("provider_priority")
    if provider_priority is not None:
        if not isinstance(provider_priority, list) or not all(
            isinstance(item, str) for item in provider_priority
        ):
            raise HTTPException(status_code=422, detail="provider_priority must be a list of provider ids")
        unknown = [item for item in provider_priority if item not in PROVIDER_IDS]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown provider in provider_priority: {', '.join(unknown)}",
            )

    auto_fallback = payload.get("auto_fallback")
    if auto_fallback is not None and not isinstance(auto_fallback, bool):
        raise HTTPException(status_code=422, detail="auto_fallback must be true or false")

    api_keys: dict[str, str | None] = {}
    for provider in CLOUD_PROVIDER_IDS:
        field = f"{provider}_api_key"
        if field not in payload:
            continue
        value = payload.get(field)
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"{provider} API key must be a string")
        if value and len(value.strip()) < 20:
            raise HTTPException(status_code=422, detail=f"{provider} API key looks too short")
        api_keys[provider] = value

    try:
        update_provider_settings(
            ollama_url=ollama_url.strip() if isinstance(ollama_url, str) else None,
            ollama_model=ollama_model.strip() if isinstance(ollama_model, str) else None,
            openrouter_model=openrouter_model.strip() if isinstance(openrouter_model, str) else None,
            gemini_model=gemini_model,
            groq_model=groq_model,
            openrouter_api_key=api_keys.get("openrouter"),
            gemini_api_key=api_keys.get("gemini"),
            groq_api_key=api_keys.get("groq"),
            ai_provider=ai_provider,
            provider_priority=provider_priority,
            auto_fallback=auto_fallback,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if payload.get("theme") is not None:
        theme = payload.get("theme")
        if theme not in {"dark", "light"}:
            raise HTTPException(status_code=422, detail="Theme must be dark or light")
        with get_db() as db:
            setting_set(db, "theme", theme)
    return _settings_payload()


@router.get("/providers")
async def list_providers() -> dict:
    statuses = await all_providers_status()
    settings = get_provider_settings()
    return {
        "providers": statuses,
        "chain": build_provider_chain(settings),
        "selected": settings["ai_provider"],
        "auto_fallback": settings["auto_fallback"],
        "free_only": True,
    }


@router.get("/providers/status")
async def provider_status() -> dict:
    return await provider_chain_status()


@router.get("/providers/chain")
async def read_provider_chain() -> dict:
    return await provider_chain_status()


@router.post("/providers/chain/test")
async def test_provider_chain() -> dict:
    try:
        result = await generate_text(
            "Reply with exactly: OK",
            system="You are a connection test. Reply with a single word.",
            temperature=0,
            max_tokens=8,
            json_mode=False,
            operation="chain_test",
        )
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    result["chain_status"] = await provider_chain_status()
    return result


@router.post("/providers/ollama/test")
@router.post("/system/ollama/test")
async def test_ollama(payload: dict | None = None) -> dict:
    payload = payload or {}
    try:
        status = await ollama_test(payload.get("base_url"), payload.get("model"))
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    status["selected_model"] = status.get("model")
    status["selected_model_available"] = status.get("selected_model_available")
    return status


@router.post("/providers/openrouter/test")
async def test_openrouter() -> dict:
    return await openrouter_test()


@router.get("/providers/openrouter/models")
async def get_openrouter_models() -> dict:
    try:
        models = await openrouter_free_models(force=True)
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"models": models, "free_only": True, "verified": True}


@router.get("/providers/openrouter/status")
async def read_openrouter_status() -> dict:
    return await openrouter_status()


@router.post("/providers/gemini/test")
async def test_gemini() -> dict:
    return await gemini_test()


@router.get("/providers/gemini/models")
async def get_gemini_models() -> dict:
    settings = get_provider_settings()
    try:
        models = await gemini_free_models(force=True)
    except ProviderError as exc:
        return _models_unavailable(gemini_known_models(), exc, settings["gemini_key_configured"])
    return {"models": models, "free_only": True, "verified": True}


@router.get("/providers/gemini/status")
async def read_gemini_status() -> dict:
    return await gemini_status()


@router.post("/providers/groq/test")
async def test_groq() -> dict:
    return await groq_test()


@router.get("/providers/groq/models")
async def get_groq_models() -> dict:
    settings = get_provider_settings()
    try:
        models = await groq_free_models(force=True)
    except ProviderError as exc:
        return _models_unavailable(groq_known_models(), exc, settings["groq_key_configured"])
    return {"models": models, "free_only": True, "verified": True}


@router.get("/providers/groq/status")
async def read_groq_status() -> dict:
    return await groq_status()


@router.get("/ai/usage")
def ai_usage(limit: int = 50) -> dict:
    limit = max(1, min(limit, 200))
    with get_db() as db:
        rows = db.execute("SELECT * FROM ai_usage ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        summary = db.execute(
            """
            SELECT provider, model, COUNT(*) AS requests,
                   SUM(COALESCE(prompt_tokens,0)) AS prompt_tokens,
                   SUM(COALESCE(completion_tokens,0)) AS completion_tokens
            FROM ai_usage GROUP BY provider, model ORDER BY requests DESC
            """
        ).fetchall()
        total = db.execute("SELECT COUNT(*) AS count FROM ai_usage").fetchone()["count"]
    return {
        "usage": [dict(row) for row in rows],
        "summary": [dict(row) for row in summary],
        "total_requests": total,
        "free_only": True,
    }
