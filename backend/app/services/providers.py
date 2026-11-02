from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import (
    GEMINI_BASE_URL,
    GEMINI_TIMEOUT_SECONDS,
    GROQ_BASE_URL,
    GROQ_TIMEOUT_SECONDS,
    OLLAMA_DEFAULT_MODEL,
    OLLAMA_DEFAULT_URL,
    OLLAMA_TIMEOUT_SECONDS,
    OPENROUTER_BASE_URL,
    OPENROUTER_TIMEOUT_SECONDS,
)
from ..db import get_db, setting_get, utc_now
from .secrets import get_secret, set_secret

PROVIDER_IDS = ("openrouter", "gemini", "groq", "ollama")
CLOUD_PROVIDER_IDS = ("openrouter", "gemini", "groq")
DEFAULT_PRIORITY = ["openrouter", "gemini", "groq", "ollama"]
LOCAL_OLLAMA_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _require_local_ollama_url(base_url: str) -> str:
    """Reject remote Ollama URLs before any request leaves this computer.

    Settings already validates the saved URL. This guard protects every direct provider call,
    including connection tests and future callers that pass a base URL explicitly.
    """
    parsed = urlparse((base_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ProviderError(
            "Ollama URL must be a valid http(s) URL.",
            status_code=422,
            provider="ollama",
            kind="config",
        )
    if parsed.hostname not in LOCAL_OLLAMA_HOSTS:
        raise ProviderError(
            "Ollama must run on localhost. Cloud Ollama hosts are not allowed in FREE_ONLY mode.",
            status_code=422,
            provider="ollama",
            kind="config",
        )
    return (base_url or "").strip().rstrip("/")

PROVIDER_NAMES = {
    "openrouter": "OpenRouter (free models only)",
    "gemini": "Google Gemini (free tier)",
    "groq": "Groq (free plan)",
    "ollama": "Ollama (local)",
}

PROVIDER_PRICING = {
    "openrouter": "free_models_only",
    "gemini": "free_tier_only",
    "groq": "free_plan_only",
    "ollama": "local",
}

# Gemini free-tier text models. Google marks the Flash, Flash-Lite and Pro families as having a
# free tier; Gemini 4 Argon is explicitly paid-only and is therefore excluded. We reject anything
# outside this pattern before a request is sent.
FREE_GEMINI_RE = re.compile(
    r"^gemini-(2\.0|2\.5|3(?:\.\d+)?)-(flash|pro)(?:-lite)?(?:-preview)?(?:-\d{2}-\d{4})?$"
)
GEMINI_KNOWN_FREE_MODELS = [
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
    {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash-Lite"},
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash"},
]

# Groq free-plan text models, from the official Free Plan Limits table. Models marked
# "Enterprise / Contact Sales", speech models and guard models are excluded.
GROQ_KNOWN_FREE_MODELS = [
    {"id": "openai/gpt-oss-120b", "name": "OpenAI GPT-OSS 120B"},
    {"id": "openai/gpt-oss-20b", "name": "OpenAI GPT-OSS 20B"},
    {"id": "qwen/qwen3.8-27b", "name": "Qwen 3.8 27B"},
]
GROQ_FREE_MODEL_IDS = {item["id"] for item in GROQ_KNOWN_FREE_MODELS}

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


def gemini_known_models() -> list[dict[str, Any]]:
    return [
        {**item, "context_length": None, "pricing": "free_tier", "free": True, "requires_key": True}
        for item in GEMINI_KNOWN_FREE_MODELS
    ]


def groq_known_models() -> list[dict[str, Any]]:
    return [
        {**item, "context_length": None, "pricing": "free_plan", "free": True, "requires_key": True}
        for item in GROQ_KNOWN_FREE_MODELS
    ]

_OLLAMA_SEMAPHORE = asyncio.Semaphore(1)
_MODEL_CACHE: dict[str, dict[str, Any]] = {
    "openrouter": {"at": 0.0, "models": []},
    "gemini": {"at": 0.0, "models": []},
    "groq": {"at": 0.0, "models": []},
}
_MODEL_CACHE_TTL = 600.0


class ProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int = 502,
        provider: str = "provider",
        *,
        kind: str = "error",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider
        self.kind = kind
        self.retry_after = retry_after


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed
    except (TypeError, json.JSONDecodeError):
        return default


def _normalize_priority(value: Any) -> list[str]:
    order: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item in PROVIDER_IDS and item not in order:
                order.append(item)
    for provider in DEFAULT_PRIORITY:
        if provider not in order:
            order.append(provider)
    return order


def get_provider_settings() -> dict[str, Any]:
    with get_db() as db:
        priority = _normalize_priority(
            _json_load(setting_get(db, "provider_priority", json.dumps(DEFAULT_PRIORITY)), [])
        )
        auto_fallback_raw = (setting_get(db, "auto_fallback", "true") or "true").lower()
        return {
            "ollama_url": setting_get(db, "ollama_url", OLLAMA_DEFAULT_URL) or OLLAMA_DEFAULT_URL,
            "ollama_model": setting_get(db, "ollama_model", OLLAMA_DEFAULT_MODEL)
            or OLLAMA_DEFAULT_MODEL,
            "openrouter_model": setting_get(db, "openrouter_model", "") or "",
            "gemini_model": setting_get(db, "gemini_model", DEFAULT_GEMINI_MODEL)
            or DEFAULT_GEMINI_MODEL,
            "groq_model": setting_get(db, "groq_model", DEFAULT_GROQ_MODEL) or DEFAULT_GROQ_MODEL,
            "ai_provider": setting_get(db, "ai_provider", "ollama") or "ollama",
            "provider_priority": priority,
            "auto_fallback": auto_fallback_raw in {"1", "true", "yes", "on"},
            "openrouter_key_configured": bool(get_secret("openrouter_api_key")),
            "gemini_key_configured": bool(get_secret("gemini_api_key")),
            "groq_key_configured": bool(get_secret("groq_api_key")),
        }


def _setting_write(db: Any, key: str, value: str) -> None:
    db.execute(
        "INSERT INTO settings(key,value,updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, utc_now()),
    )


def update_provider_settings(
    ollama_url: str | None = None,
    ollama_model: str | None = None,
    openrouter_model: str | None = None,
    gemini_model: str | None = None,
    groq_model: str | None = None,
    openrouter_api_key: str | None = None,
    gemini_api_key: str | None = None,
    groq_api_key: str | None = None,
    ai_provider: str | None = None,
    provider_priority: list[str] | None = None,
    auto_fallback: bool | None = None,
) -> None:
    with get_db() as db:
        if ollama_url is not None:
            _setting_write(db, "ollama_url", ollama_url.rstrip("/"))
        if ollama_model is not None:
            _setting_write(db, "ollama_model", ollama_model)
        if openrouter_model is not None:
            _setting_write(db, "openrouter_model", openrouter_model)
        if gemini_model is not None:
            _setting_write(db, "gemini_model", gemini_model)
        if groq_model is not None:
            _setting_write(db, "groq_model", groq_model)
        if ai_provider is not None:
            if ai_provider not in PROVIDER_IDS:
                raise ProviderError("Unsupported AI provider", status_code=422, kind="config")
            _setting_write(db, "ai_provider", ai_provider)
        if provider_priority is not None:
            _setting_write(
                db, "provider_priority", json.dumps(_normalize_priority(provider_priority))
            )
        if auto_fallback is not None:
            _setting_write(db, "auto_fallback", "true" if auto_fallback else "false")

    for key, value in (
        ("openrouter_api_key", openrouter_api_key),
        ("gemini_api_key", gemini_api_key),
        ("groq_api_key", groq_api_key),
    ):
        if value is not None:
            set_secret(key, value.strip() or None)
            provider = key.replace("_api_key", "")
            _MODEL_CACHE[provider]["at"] = 0.0
            _MODEL_CACHE[provider]["models"] = []


# ---------------------------------------------------------------------------
# Provider health / cooldowns
# ---------------------------------------------------------------------------


def _health_load() -> dict[str, Any]:
    with get_db() as db:
        data = _json_load(setting_get(db, "provider_health", "{}"), {})
    return data if isinstance(data, dict) else {}


def _health_save(health: dict[str, Any]) -> None:
    try:
        with get_db() as db:
            _setting_write(db, "provider_health", json.dumps(health))
    except Exception:
        # Health bookkeeping must never break generation.
        pass


def _cooldown_seconds(health: dict[str, Any], provider: str) -> int:
    entry = health.get(provider) or {}
    until = entry.get("cooldown_until")
    if not until:
        return 0
    try:
        parsed = datetime.fromisoformat(str(until))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((parsed - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError):
        return 0


def provider_cooldown(provider: str) -> int:
    return _cooldown_seconds(_health_load(), provider)


def _mark_success(provider: str, model: str) -> None:
    health = _health_load()
    entry = health.get(provider) if isinstance(health.get(provider), dict) else {}
    entry.update(
        {
            "last_success": utc_now(),
            "last_error": None,
            "last_error_kind": None,
            "cooldown_until": None,
            "failures": 0,
            "model": model,
        }
    )
    health[provider] = entry
    _health_save(health)


def _mark_error(provider: str, model: str, exc: ProviderError) -> None:
    health = _health_load()
    entry = health.get(provider) if isinstance(health.get(provider), dict) else {}
    cooldown = 0
    if exc.kind in {"quota", "payment"}:
        cooldown = int(exc.retry_after or (86400 if exc.kind == "payment" else 900))
        cooldown = max(30, min(cooldown, 86400))
    elif exc.kind in {"transient", "network"}:
        cooldown = int(exc.retry_after or 30)
    entry.update(
        {
            "last_attempt": utc_now(),
            "last_failure": utc_now(),
            "last_error": str(exc),
            "last_error_kind": exc.kind,
            "failures": int(entry.get("failures") or 0) + 1,
            "model": model,
        }
    )
    if cooldown:
        entry["cooldown_until"] = (
            datetime.now(timezone.utc) + timedelta(seconds=cooldown)
        ).isoformat(timespec="seconds")
    health[provider] = entry
    _health_save(health)


def _health_summary(provider: str) -> dict[str, Any]:
    health = _health_load()
    entry = health.get(provider) if isinstance(health.get(provider), dict) else {}
    return {
        "last_verified": entry.get("last_success"),
        "last_error": entry.get("last_error"),
        "last_error_kind": entry.get("last_error_kind"),
        "last_attempt": entry.get("last_attempt"),
        "failures": int(entry.get("failures") or 0),
        "cooldown_seconds": _cooldown_seconds(health, provider),
    }


def log_usage(
    provider: str,
    model: str,
    operation: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    duration_ms: int,
) -> None:
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO ai_usage(provider,model,operation,prompt_tokens,completion_tokens,duration_ms,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (provider, model, operation, prompt_tokens, completion_tokens, duration_ms, utc_now()),
            )
    except Exception:
        # Usage accounting must never break generation.
        pass


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------


async def get_ollama_models(base_url: str | None = None) -> list[dict[str, Any]]:
    settings = get_provider_settings()
    base = _require_local_ollama_url(base_url or settings["ollama_url"])
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{base}/api/tags")
    except httpx.ConnectError as exc:
        raise ProviderError(
            f"Ollama is not reachable at {base}. Start it with 'ollama serve' and try again.",
            provider="ollama",
            kind="network",
        ) from exc
    except httpx.TimeoutException as exc:
        raise ProviderError(
            "Ollama did not respond in time.", provider="ollama", kind="network"
        ) from exc
    if response.status_code != 200:
        raise ProviderError(
            f"Ollama returned HTTP {response.status_code}.", provider="ollama", kind="transient"
        )
    payload = response.json()
    return payload.get("models") or []


async def ollama_status(base_url: str | None = None, model: str | None = None) -> dict[str, Any]:
    settings = get_provider_settings()
    base = (base_url or settings["ollama_url"]).rstrip("/")
    selected = model or settings["ollama_model"]
    health = _health_summary("ollama")
    status: dict[str, Any] = {
        "id": "ollama",
        "name": PROVIDER_NAMES["ollama"],
        "kind": "text",
        "pricing": PROVIDER_PRICING["ollama"],
        "free": True,
        "capabilities": ["text", "strategy", "copywriting", "edit planning"],
        "available": False,
        "configured": True,
        "model": selected,
        "models": [],
        "base_url": base,
        "selected_model_available": None,
        "error": None,
        "requires_key": False,
        "limits": "Local inference. No token cost and no quota, limited only by this computer.",
        **health,
    }
    try:
        models = await get_ollama_models(base)
        names = [item.get("name") for item in models if item.get("name")]
        status["models"] = names
        status["available"] = True
        status["selected_model_available"] = selected in names
        if selected not in names:
            status["error"] = (
                f"Model '{selected}' is not installed. Choose one of the installed models in CreativeForge Settings."
            )
    except ProviderError as exc:
        status["error"] = str(exc)
    except Exception as exc:
        status["error"] = f"Could not inspect Ollama: {exc}"
    return status


async def ollama_test(base_url: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Check the local server and installed model list without loading the model.

    Real inference is verified by the chat endpoint. Running a generation here made a
    "connection test" take up to a minute on the reference CPU and blocked the next model call.
    """
    settings = get_provider_settings()
    base = _require_local_ollama_url(base_url or settings["ollama_url"])
    selected = model or settings["ollama_model"]
    status = await ollama_status(base, selected)
    status["connection_check"] = "server_and_models"
    if status["available"] and not status["selected_model_available"]:
        status["error"] = status["error"] or f"Model '{selected}' is not installed."
    return status


async def _ollama_chat(
    prompt: str,
    system: str | None,
    model: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    base_url: str,
    operation: str,
) -> dict[str, Any]:
    base_url = _require_local_ollama_url(base_url)
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "5m",
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if json_mode:
        payload["format"] = "json"
    started = time.monotonic()
    async with _OLLAMA_SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
                response = await client.post(f"{base_url}/api/chat", json=payload)
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Ollama is not reachable at {base_url}. Start it with 'ollama serve'.",
                provider="ollama",
                kind="network",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"The local model '{model}' took longer than {int(OLLAMA_TIMEOUT_SECONDS)}s. "
                "Try a shorter request or the smaller qwen2.5:1.5b model.",
                provider="ollama",
                kind="transient",
            ) from exc
    if response.status_code == 404:
        raise ProviderError(
            f"Ollama model '{model}' is not installed. Choose one of the installed models in CreativeForge Settings.",
            provider="ollama",
            kind="config",
        )
    if response.status_code != 200:
        message = "Ollama request failed."
        try:
            message = response.json().get("error") or message
        except Exception:
            pass
        raise ProviderError(
            f"{message} (HTTP {response.status_code})", provider="ollama", kind="transient"
        )
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise ProviderError(
            "Ollama returned an invalid response.", provider="ollama", kind="transient"
        ) from exc
    content = ((body.get("message") or {}).get("content") or "").strip()
    if not content:
        raise ProviderError(
            "The local model returned an empty response.", provider="ollama", kind="transient"
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    log_usage(
        "ollama",
        model,
        operation,
        body.get("prompt_eval_count"),
        body.get("eval_count"),
        duration_ms,
    )
    return {
        "content": content,
        "provider": "ollama",
        "model": model,
        "prompt_tokens": body.get("prompt_eval_count"),
        "completion_tokens": body.get("eval_count"),
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# OpenRouter (free-priced models only)
# ---------------------------------------------------------------------------


def _openrouter_headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://127.0.0.1:5173",
        "X-Title": "CreativeForge AI",
    }


async def openrouter_free_models(force: bool = False) -> list[dict[str, Any]]:
    now = time.monotonic()
    cache = _MODEL_CACHE["openrouter"]
    if not force and cache["models"] and now - cache["at"] < _MODEL_CACHE_TTL:
        return cache["models"]
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{OPENROUTER_BASE_URL}/models")
        if response.status_code != 200:
            raise ProviderError(
                f"OpenRouter model list returned HTTP {response.status_code}.",
                provider="openrouter",
                kind="transient",
            )
        payload = response.json()
        free: list[dict[str, Any]] = []
        for model in payload.get("data") or []:
            model_id = str(model.get("id") or "")
            if not model_id.endswith(":free"):
                continue
            pricing = model.get("pricing") or {}
            prompt_price = str(pricing.get("prompt", "0"))
            completion_price = str(pricing.get("completion", "0"))
            if prompt_price not in {"0", "0.0", "0.00"} or completion_price not in {
                "0",
                "0.0",
                "0.00",
            }:
                continue
            free.append(
                {
                    "id": model_id,
                    "name": model.get("name") or model_id,
                    "context_length": model.get("context_length"),
                    "pricing": "free",
                    "free": True,
                }
            )
        free.sort(key=lambda item: item["name"].lower())
        cache.update({"at": now, "models": free})
        return free
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(
            f"Could not reach OpenRouter: {exc}", provider="openrouter", kind="network"
        ) from exc


async def openrouter_key_info() -> dict[str, Any]:
    key = get_secret("openrouter_api_key")
    if not key:
        raise ProviderError(
            "OpenRouter API key is missing.", provider="openrouter", kind="config"
        )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{OPENROUTER_BASE_URL}/key", headers=_openrouter_headers(key)
            )
    except httpx.TimeoutException as exc:
        raise ProviderError(
            "OpenRouter key check timed out.", provider="openrouter", kind="network"
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Could not reach OpenRouter: {exc}", provider="openrouter", kind="network"
        ) from exc
    if response.status_code in {401, 403}:
        raise ProviderError(
            "OpenRouter rejected the API key.", provider="openrouter", kind="auth"
        )
    if response.status_code != 200:
        raise ProviderError(
            f"OpenRouter key check returned HTTP {response.status_code}.",
            provider="openrouter",
            kind="transient",
        )
    data = (response.json() or {}).get("data") or {}
    return {
        "label": data.get("label"),
        "is_free_tier": data.get("is_free_tier"),
        "limit": data.get("limit"),
        "limit_remaining": data.get("limit_remaining"),
        "usage": data.get("usage"),
    }


async def openrouter_status() -> dict[str, Any]:
    settings = get_provider_settings()
    key_set = settings["openrouter_key_configured"]
    selected = settings["openrouter_model"]
    health = _health_summary("openrouter")
    status: dict[str, Any] = {
        "id": "openrouter",
        "name": PROVIDER_NAMES["openrouter"],
        "kind": "text",
        "pricing": PROVIDER_PRICING["openrouter"],
        "free": True,
        "capabilities": ["text", "strategy", "copywriting", "edit planning"],
        "available": False,
        "configured": key_set,
        "model": selected or None,
        "models": [],
        "error": None,
        "requires_key": True,
        "limits": "Only models ending in ':free' are allowed. OpenRouter currently limits free use to 20 requests/minute and 50 requests/day for accounts with under 10 credits. No paid fallback exists.",
        "billing_note": "Free models are zero-priced. Requests to ':free' models do not spend credits.",
        **health,
    }
    if not key_set:
        status["error"] = "Add an OpenRouter API key to enable this free provider."
        return status
    if not selected:
        status["error"] = "Choose one of the free OpenRouter models."
        return status
    if not selected.endswith(":free"):
        status["error"] = "Paid model rejected: this application only permits models ending in :free."
        return status
    try:
        status["account"] = await openrouter_key_info()
        models = await openrouter_free_models()
        status["models"] = [item["id"] for item in models]
        status["available"] = any(item["id"] == selected for item in models)
        if not status["available"]:
            status["error"] = (
                "The selected model is not in OpenRouter's current free-model list. "
                "Choose a currently free model or use local Ollama."
            )
        elif health["cooldown_seconds"]:
            status["error"] = (
                "OpenRouter is cooling down after a free-quota or rate-limit response. "
                f"Try again in {health['cooldown_seconds']} seconds."
            )
    except ProviderError as exc:
        status["available"] = False
        status["error"] = str(exc)
    return status


async def openrouter_test() -> dict[str, Any]:
    status = await openrouter_status()
    if not status["available"]:
        return status
    settings = get_provider_settings()
    model = settings["openrouter_model"]
    try:
        result = await openrouter_chat(
            prompt="Reply with exactly: OK",
            system="You are a connection test. Reply with a single word.",
            model=model,
            temperature=0,
            max_tokens=8,
            json_mode=False,
            operation="connection_test",
        )
        status.update(
            {
                "test_reply": result["content"][:80],
                "error": None,
                "available": True,
                "last_verified": utc_now(),
            }
        )
    except ProviderError as exc:
        status["available"] = False
        status["error"] = str(exc)
        status.update(_health_summary("openrouter"))
    return status


def _provider_http_error(
    provider: str, response: httpx.Response, model: str
) -> ProviderError:
    detail = ""
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            detail = str(error.get("message") or "")
        elif isinstance(error, str):
            detail = error
        elif isinstance(body, dict):
            detail = str(body.get("message") or body.get("detail") or "")
    except Exception:
        detail = response.text[:400]
    detail = detail.strip()[:500]
    suffix = f" {detail}" if detail else ""
    if response.status_code == 429:
        retry_after = None
        raw_retry = response.headers.get("retry-after")
        if raw_retry:
            try:
                retry_after = float(raw_retry)
            except ValueError:
                pass
        return ProviderError(
            f"{PROVIDER_NAMES.get(provider, provider)} free quota or rate limit was reached.{suffix}",
            status_code=429,
            provider=provider,
            kind="quota",
            retry_after=retry_after,
        )
    if response.status_code == 402:
        return ProviderError(
            f"{PROVIDER_NAMES.get(provider, provider)} reported that this request would require payment. "
            "It was blocked. No paid fallback will be used.",
            status_code=402,
            provider=provider,
            kind="payment",
        )
    if response.status_code in {401, 403}:
        return ProviderError(
            f"{PROVIDER_NAMES.get(provider, provider)} rejected the API key or model access.{suffix}",
            status_code=403,
            provider=provider,
            kind="auth",
        )
    if response.status_code == 404:
        return ProviderError(
            f"The model '{model}' is not available for this provider.{suffix}",
            status_code=404,
            provider=provider,
            kind="config",
        )
    if response.status_code == 400:
        return ProviderError(
            f"{PROVIDER_NAMES.get(provider, provider)} rejected the request: {detail or 'invalid request'}",
            status_code=422,
            provider=provider,
            kind="config",
        )
    return ProviderError(
        f"{PROVIDER_NAMES.get(provider, provider)} returned HTTP {response.status_code}.{suffix}",
        status_code=502,
        provider=provider,
        kind="transient",
    )


async def openrouter_chat(
    prompt: str,
    system: str | None,
    model: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    operation: str,
) -> dict[str, Any]:
    if not model.endswith(":free"):
        raise ProviderError(
            "Paid model rejected. Only OpenRouter models ending in ':free' may be used.",
            status_code=403,
            provider="openrouter",
            kind="blocked_paid",
        )
    key = get_secret("openrouter_api_key")
    if not key:
        raise ProviderError(
            "OpenRouter is not configured. Add an API key in AI settings.",
            provider="openrouter",
            kind="config",
        )
    # Fail closed: never send a request unless the current catalog confirms the model is free.
    # A catalog/network failure falls through to the next free provider in the chain.
    models = await openrouter_free_models()
    if not any(item["id"] == model for item in models):
        raise ProviderError(
            "Selected model is not in OpenRouter's current free-model catalog. It was blocked "
            "before any request was sent.",
            status_code=403,
            provider="openrouter",
            kind="blocked_paid",
        )
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if json_mode:
        messages.append(
            {
                "role": "system",
                "content": "Return only a valid JSON object. Do not wrap it in markdown fences.",
            }
        )
    messages.append({"role": "user", "content": prompt})
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=OPENROUTER_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=_openrouter_headers(key),
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
    except httpx.TimeoutException as exc:
        raise ProviderError(
            "OpenRouter did not respond in time.", provider="openrouter", kind="network"
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Could not reach OpenRouter: {exc}", provider="openrouter", kind="network"
        ) from exc
    if response.status_code != 200:
        raise _provider_http_error("openrouter", response, model)
    body = response.json()
    content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise ProviderError(
            "OpenRouter returned an empty response.", provider="openrouter", kind="transient"
        )
    usage = body.get("usage") or {}
    duration_ms = int((time.monotonic() - started) * 1000)
    log_usage(
        "openrouter",
        model,
        operation,
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        duration_ms,
    )
    return {
        "content": content.strip(),
        "provider": "openrouter",
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Google Gemini (free tier only)
# ---------------------------------------------------------------------------


def is_free_gemini_model(model: str) -> bool:
    model_id = model.strip().removeprefix("models/")
    return bool(FREE_GEMINI_RE.fullmatch(model_id))


def _gemini_key() -> str:
    key = get_secret("gemini_api_key")
    if not key:
        raise ProviderError(
            "Gemini API key is missing.", provider="gemini", kind="config"
        )
    return key


async def gemini_free_models(force: bool = False) -> list[dict[str, Any]]:
    now = time.monotonic()
    cache = _MODEL_CACHE["gemini"]
    if not force and cache["models"] and now - cache["at"] < _MODEL_CACHE_TTL:
        return cache["models"]
    key = _gemini_key()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{GEMINI_BASE_URL}/models",
                params={"pageSize": 1000},
                headers={"x-goog-api-key": key},
            )
    except httpx.TimeoutException as exc:
        raise ProviderError(
            "Gemini model list timed out.", provider="gemini", kind="network"
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Could not reach Gemini: {exc}", provider="gemini", kind="network"
        ) from exc
    if response.status_code in {401, 403}:
        raise ProviderError(
            "Gemini rejected the API key.", provider="gemini", kind="auth"
        )
    if response.status_code == 429:
        raise _provider_http_error("gemini", response, "model-list")
    if response.status_code != 200:
        raise ProviderError(
            f"Gemini model list returned HTTP {response.status_code}.",
            provider="gemini",
            kind="transient",
        )
    models: list[dict[str, Any]] = []
    for item in (response.json() or {}).get("models") or []:
        model_id = str(item.get("name") or "").removeprefix("models/")
        if not is_free_gemini_model(model_id):
            continue
        methods = item.get("supportedGenerationMethods") or []
        if methods and "generateContent" not in methods:
            continue
        models.append(
            {
                "id": model_id,
                "name": item.get("displayName") or model_id,
                "context_length": item.get("inputTokenLimit"),
                "output_token_limit": item.get("outputTokenLimit"),
                "pricing": "free_tier",
                "free": True,
            }
        )
    models.sort(key=lambda item: item["id"])
    if models:
        cache.update({"at": now, "models": models})
    return models


async def gemini_status() -> dict[str, Any]:
    settings = get_provider_settings()
    key_set = settings["gemini_key_configured"]
    selected = settings["gemini_model"]
    health = _health_summary("gemini")
    status: dict[str, Any] = {
        "id": "gemini",
        "name": PROVIDER_NAMES["gemini"],
        "kind": "text",
        "pricing": PROVIDER_PRICING["gemini"],
        "free": True,
        "capabilities": ["text", "strategy", "copywriting", "edit planning"],
        "available": False,
        "configured": key_set,
        "model": selected,
        "models": [],
        "error": None,
        "requires_key": True,
        "limits": "Gemini free-tier text models only. Free-tier quotas reset daily and are controlled by Google. A Google Cloud project with billing enabled may be charged by Google; use a no-billing AI Studio project to stay at zero cost.",
        "billing_note": "This app only sends requests to the free-tier model families. It cannot disable provider-side billing; confirm your Google project has no billing account.",
        **health,
    }
    if not key_set:
        status["error"] = "Add a Google AI Studio API key to enable this free provider."
        return status
    if not is_free_gemini_model(selected):
        status["error"] = (
            "Paid or non-text model rejected: this application only permits Gemini free-tier "
            "Flash, Flash-Lite and Pro text models."
        )
        return status
    try:
        models = await gemini_free_models()
        status["models"] = [item["id"] for item in models]
        status["available"] = any(item["id"] == selected for item in models)
        if not status["available"]:
            status["error"] = (
                "The selected model is not in Gemini's current free-tier text model list."
            )
        elif health["cooldown_seconds"]:
            status["error"] = (
                "Gemini is cooling down after a free-quota or rate-limit response. "
                f"Try again in {health['cooldown_seconds']} seconds."
            )
    except ProviderError as exc:
        status["available"] = False
        status["error"] = str(exc)
    return status


async def gemini_test() -> dict[str, Any]:
    status = await gemini_status()
    if not status["available"]:
        return status
    settings = get_provider_settings()
    try:
        result = await gemini_chat(
            prompt="Reply with exactly: OK",
            system="You are a connection test. Reply with a single word.",
            model=settings["gemini_model"],
            temperature=0,
            max_tokens=8,
            json_mode=False,
            operation="connection_test",
        )
        status.update(
            {
                "test_reply": result["content"][:80],
                "error": None,
                "available": True,
                "last_verified": utc_now(),
            }
        )
    except ProviderError as exc:
        status["available"] = False
        status["error"] = str(exc)
        status.update(_health_summary("gemini"))
    return status


async def gemini_chat(
    prompt: str,
    system: str | None,
    model: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    operation: str,
) -> dict[str, Any]:
    if not is_free_gemini_model(model):
        raise ProviderError(
            "Paid or non-text Gemini model rejected. Only free-tier Flash, Flash-Lite and Pro "
            "text models are permitted.",
            status_code=403,
            provider="gemini",
            kind="blocked_paid",
        )
    key = _gemini_key()
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=GEMINI_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{GEMINI_BASE_URL}/models/{model}:generateContent",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise ProviderError(
            "Gemini did not respond in time.", provider="gemini", kind="network"
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Could not reach Gemini: {exc}", provider="gemini", kind="network"
        ) from exc
    if response.status_code != 200:
        error = _provider_http_error("gemini", response, model)
        if response.status_code == 429:
            # Gemini often embeds "Please retry in 34.5s" in the message.
            try:
                detail = json.dumps(response.json())
            except Exception:
                detail = response.text
            match = re.search(r"retry in ([\d.]+)s", detail, re.IGNORECASE)
            if match and error.retry_after is None:
                error.retry_after = float(match.group(1))
        raise error
    payload = response.json()
    candidates = payload.get("candidates") or []
    parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts")) or []
    content = "".join(str(part.get("text") or "") for part in parts).strip()
    if not content:
        block_reason = (payload.get("promptFeedback") or {}).get("blockReason")
        message = "Gemini returned an empty response."
        if block_reason:
            message = f"Gemini blocked the request ({block_reason})."
        raise ProviderError(message, provider="gemini", kind="transient")
    usage = payload.get("usageMetadata") or {}
    duration_ms = int((time.monotonic() - started) * 1000)
    log_usage(
        "gemini",
        model,
        operation,
        usage.get("promptTokenCount"),
        usage.get("candidatesTokenCount"),
        duration_ms,
    )
    return {
        "content": content,
        "provider": "gemini",
        "model": model,
        "prompt_tokens": usage.get("promptTokenCount"),
        "completion_tokens": usage.get("candidatesTokenCount"),
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Groq (free plan only)
# ---------------------------------------------------------------------------


def is_free_groq_model(model: str) -> bool:
    return model in GROQ_FREE_MODEL_IDS


def _groq_key() -> str:
    key = get_secret("groq_api_key")
    if not key:
        raise ProviderError("Groq API key is missing.", provider="groq", kind="config")
    return key


async def groq_free_models(force: bool = False) -> list[dict[str, Any]]:
    now = time.monotonic()
    cache = _MODEL_CACHE["groq"]
    if not force and cache["models"] and now - cache["at"] < _MODEL_CACHE_TTL:
        return cache["models"]
    key = _groq_key()
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{GROQ_BASE_URL}/models",
                headers={"Authorization": f"Bearer {key}"},
            )
    except httpx.TimeoutException as exc:
        raise ProviderError(
            "Groq model list timed out.", provider="groq", kind="network"
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Could not reach Groq: {exc}", provider="groq", kind="network"
        ) from exc
    if response.status_code in {401, 403}:
        raise ProviderError("Groq rejected the API key.", provider="groq", kind="auth")
    if response.status_code == 429:
        raise _provider_http_error("groq", response, "model-list")
    if response.status_code != 200:
        raise ProviderError(
            f"Groq model list returned HTTP {response.status_code}.",
            provider="groq",
            kind="transient",
        )
    available = {
        str(item.get("id"))
        for item in (response.json() or {}).get("data") or []
        if item.get("id")
    }
    models = [
        {**item, "context_length": None, "pricing": "free_plan", "free": True}
        for item in GROQ_KNOWN_FREE_MODELS
        if item["id"] in available
    ]
    if models:
        cache.update({"at": now, "models": models})
    return models


async def groq_status() -> dict[str, Any]:
    settings = get_provider_settings()
    key_set = settings["groq_key_configured"]
    selected = settings["groq_model"]
    health = _health_summary("groq")
    status: dict[str, Any] = {
        "id": "groq",
        "name": PROVIDER_NAMES["groq"],
        "kind": "text",
        "pricing": PROVIDER_PRICING["groq"],
        "free": True,
        "capabilities": ["text", "strategy", "copywriting", "edit planning"],
        "available": False,
        "configured": key_set,
        "model": selected,
        "models": [],
        "error": None,
        "requires_key": True,
        "limits": "Groq free-plan text models only. Groq publishes per-model daily request/token limits and they can change. No paid fallback exists.",
        "billing_note": "This app only sends requests to models listed on Groq's Free Plan Limits table. Use a Groq account without a payment method to stay at zero cost.",
        **health,
    }
    if not key_set:
        status["error"] = "Add a Groq API key to enable this free provider."
        return status
    if not is_free_groq_model(selected):
        status["error"] = (
            "Paid or non-text model rejected: this application only permits models on Groq's "
            "Free Plan Limits table."
        )
        return status
    try:
        models = await groq_free_models()
        status["models"] = [item["id"] for item in models]
        status["available"] = any(item["id"] == selected for item in models)
        if not status["available"]:
            status["error"] = "The selected model is not in Groq's current free-plan model list."
        elif health["cooldown_seconds"]:
            status["error"] = (
                "Groq is cooling down after a free-quota or rate-limit response. "
                f"Try again in {health['cooldown_seconds']} seconds."
            )
    except ProviderError as exc:
        status["available"] = False
        status["error"] = str(exc)
    return status


async def groq_test() -> dict[str, Any]:
    status = await groq_status()
    if not status["available"]:
        return status
    settings = get_provider_settings()
    try:
        result = await groq_chat(
            prompt="Reply with exactly: OK",
            system="You are a connection test. Reply with a single word.",
            model=settings["groq_model"],
            temperature=0,
            max_tokens=8,
            json_mode=False,
            operation="connection_test",
        )
        status.update(
            {
                "test_reply": result["content"][:80],
                "error": None,
                "available": True,
                "last_verified": utc_now(),
            }
        )
    except ProviderError as exc:
        status["available"] = False
        status["error"] = str(exc)
        status.update(_health_summary("groq"))
    return status


async def groq_chat(
    prompt: str,
    system: str | None,
    model: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    operation: str,
) -> dict[str, Any]:
    if not is_free_groq_model(model):
        raise ProviderError(
            "Paid or non-text Groq model rejected. Only models on Groq's Free Plan Limits "
            "table are permitted.",
            status_code=403,
            provider="groq",
            kind="blocked_paid",
        )
    key = _groq_key()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if json_mode:
        messages.append(
            {
                "role": "system",
                "content": "Return only a valid JSON object. Do not wrap it in markdown fences.",
            }
        )
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=GROQ_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code == 400 and json_mode:
            # Some models do not implement JSON response_format. Retry once without it; the
            # prompt still demands a bare JSON object and the parser validates the result.
            payload.pop("response_format", None)
            async with httpx.AsyncClient(timeout=GROQ_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{GROQ_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
    except httpx.TimeoutException as exc:
        raise ProviderError(
            "Groq did not respond in time.", provider="groq", kind="network"
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Could not reach Groq: {exc}", provider="groq", kind="network"
        ) from exc
    if response.status_code != 200:
        raise _provider_http_error("groq", response, model)
    body = response.json()
    content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise ProviderError(
            "Groq returned an empty response.", provider="groq", kind="transient"
        )
    usage = body.get("usage") or {}
    duration_ms = int((time.monotonic() - started) * 1000)
    log_usage(
        "groq",
        model,
        operation,
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        duration_ms,
    )
    return {
        "content": content.strip(),
        "provider": "groq",
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# Free-only routing with automatic failover
# ---------------------------------------------------------------------------


def provider_configured(provider: str, settings: dict[str, Any]) -> bool:
    if provider == "ollama":
        return True
    if provider == "openrouter":
        return bool(
            settings["openrouter_key_configured"]
            and settings["openrouter_model"]
            and settings["openrouter_model"].endswith(":free")
        )
    if provider == "gemini":
        return bool(
            settings["gemini_key_configured"] and is_free_gemini_model(settings["gemini_model"])
        )
    if provider == "groq":
        return bool(settings["groq_key_configured"] and is_free_groq_model(settings["groq_model"]))
    return False


def build_provider_chain(settings: dict[str, Any]) -> list[str]:
    """Build the free-only chain.

    A local selection never silently sends a request to the cloud. A cloud selection may fail
    over to other configured free cloud providers and always ends at local Ollama.
    """
    selected = settings["ai_provider"]
    if selected == "ollama":
        return ["ollama"]
    chain: list[str] = []
    if provider_configured(selected, settings):
        chain.append(selected)
    if settings["auto_fallback"]:
        for provider in settings["provider_priority"]:
            if provider == "ollama":
                continue
            if provider not in chain and provider_configured(provider, settings):
                chain.append(provider)
        if "ollama" not in chain:
            chain.append("ollama")
    return chain


def _provider_settings_error(provider: str, settings: dict[str, Any]) -> ProviderError:
    if provider == "openrouter":
        if not settings["openrouter_key_configured"]:
            return ProviderError(
                "OpenRouter API key is missing.", provider=provider, kind="config"
            )
        return ProviderError(
            "Choose a free OpenRouter model ending in ':free'.",
            provider=provider,
            kind="config",
        )
    if provider == "gemini":
        if not settings["gemini_key_configured"]:
            return ProviderError("Gemini API key is missing.", provider=provider, kind="config")
        return ProviderError(
            "Choose a Gemini free-tier text model.", provider=provider, kind="config"
        )
    if provider == "groq":
        if not settings["groq_key_configured"]:
            return ProviderError("Groq API key is missing.", provider=provider, kind="config")
        return ProviderError(
            "Choose a Groq free-plan text model.", provider=provider, kind="config"
        )
    return ProviderError("No free AI provider is configured.", provider="chain", kind="config")


async def _call_provider(
    provider: str,
    settings: dict[str, Any],
    prompt: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    operation: str,
) -> dict[str, Any]:
    if provider == "ollama":
        return await _ollama_chat(
            prompt,
            system,
            settings["ollama_model"],
            temperature,
            max_tokens,
            json_mode,
            settings["ollama_url"],
            operation,
        )
    if provider == "openrouter":
        if not provider_configured("openrouter", settings):
            raise _provider_settings_error("openrouter", settings)
        return await openrouter_chat(
            prompt,
            system,
            settings["openrouter_model"],
            temperature,
            max_tokens,
            json_mode,
            operation,
        )
    if provider == "gemini":
        if not provider_configured("gemini", settings):
            raise _provider_settings_error("gemini", settings)
        return await gemini_chat(
            prompt,
            system,
            settings["gemini_model"],
            temperature,
            max_tokens,
            json_mode,
            operation,
        )
    if provider == "groq":
        if not provider_configured("groq", settings):
            raise _provider_settings_error("groq", settings)
        return await groq_chat(
            prompt,
            system,
            settings["groq_model"],
            temperature,
            max_tokens,
            json_mode,
            operation,
        )
    raise ProviderError(f"Unsupported provider: {provider}", kind="config")


def _failure_summary(attempts: list[dict[str, Any]]) -> str:
    parts = []
    for attempt in attempts:
        if attempt.get("skipped"):
            parts.append(f"{attempt['provider']}: skipped ({attempt['error']})")
        else:
            parts.append(f"{attempt['provider']}: {attempt['error']}")
    return " | ".join(parts)


async def generate_text(
    prompt: str,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1200,
    json_mode: bool = False,
    operation: str = "text",
) -> dict[str, Any]:
    settings = get_provider_settings()
    chain = build_provider_chain(settings)
    selected = settings["ai_provider"]
    if not chain:
        raise ProviderError(
            "No free AI provider is configured. Add a free provider key in AI settings or start "
            "local Ollama.",
            status_code=503,
            provider="chain",
            kind="config",
        )
    attempts: list[dict[str, Any]] = []
    last_error: ProviderError | None = None
    quota_failures = 0
    for provider in chain:
        if provider != "ollama":
            cooldown = provider_cooldown(provider)
            if cooldown > 0:
                attempts.append(
                    {
                        "provider": provider,
                        "model": None,
                        "skipped": True,
                        "kind": "cooldown",
                        "error": f"cooling down for {cooldown}s after a recent free-quota or rate-limit response",
                    }
                )
                continue
        try:
            result = await _call_provider(
                provider,
                settings,
                prompt,
                system,
                temperature,
                max_tokens,
                json_mode,
                operation,
            )
            _mark_success(provider, result["model"])
            result["fallback_used"] = provider != selected
            result["selected_provider"] = selected
            result["chain"] = chain
            result["attempts"] = attempts
            return result
        except ProviderError as exc:
            attempt_model = (
                settings["ollama_model"]
                if provider == "ollama"
                else settings.get(f"{provider}_model") or None
            )
            _mark_error(provider, attempt_model or provider, exc)
            if exc.kind in {"quota", "payment"}:
                quota_failures += 1
            attempts.append(
                {
                    "provider": provider,
                    "model": attempt_model,
                    "error": str(exc),
                    "kind": exc.kind,
                }
            )
            last_error = exc
            if provider == "ollama":
                break
            continue
    summary = _failure_summary(attempts)
    status_code = 429 if quota_failures and quota_failures == len(
        [item for item in attempts if not item.get("skipped")]
    ) else (last_error.status_code if last_error else 502)
    raise ProviderError(
        "All free AI providers in the chain failed. No paid fallback was attempted. " + summary,
        status_code=status_code,
        provider="chain",
        kind="quota" if status_code == 429 else "error",
    )


async def all_providers_status() -> list[dict[str, Any]]:
    results = await asyncio.gather(
        openrouter_status(),
        gemini_status(),
        groq_status(),
        ollama_status(),
        return_exceptions=True,
    )
    statuses: list[dict[str, Any]] = []
    for provider, result in zip(CLOUD_PROVIDER_IDS + ("ollama",), results):
        if isinstance(result, dict):
            statuses.append(result)
        else:
            statuses.append(
                {
                    "id": provider,
                    "name": PROVIDER_NAMES[provider],
                    "pricing": PROVIDER_PRICING[provider],
                    "free": True,
                    "available": False,
                    "configured": False,
                    "model": None,
                    "models": [],
                    "error": f"Status check failed: {result}",
                    **_health_summary(provider),
                }
            )
    return statuses


async def provider_chain_status() -> dict[str, Any]:
    settings = get_provider_settings()
    chain = build_provider_chain(settings)
    statuses = {item["id"]: item for item in await all_providers_status()}
    ordered = []
    for provider in chain:
        status = statuses.get(provider, {})
        ordered.append(
            {
                "id": provider,
                "name": PROVIDER_NAMES.get(provider, provider),
                "model": (
                    settings["ollama_model"]
                    if provider == "ollama"
                    else settings.get(f"{provider}_model")
                ),
                "configured": provider_configured(provider, settings),
                "available": bool(status.get("available")),
                "cooldown_seconds": int(status.get("cooldown_seconds") or 0),
                "last_verified": status.get("last_verified"),
                "error": status.get("error"),
            }
        )
    return {
        "selected": settings["ai_provider"],
        "chain": chain,
        "auto_fallback": settings["auto_fallback"],
        "free_only": True,
        "providers": ordered,
        "note": (
            "Cloud free tiers can run out. The chain skips a provider while it is cooling down, "
            "then falls back to local Ollama. It never calls a paid model."
        ),
    }
