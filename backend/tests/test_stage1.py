from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.db import init_db
from app.routers.chat import _brand_context, _project_context
from app.schemas import ChatMessage, ChatRequest
from app.services import providers
from app.services.providers import ProviderError, _ollama_chat, build_provider_chain, get_ollama_models


def test_health_and_database(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["service"] == "CreativeForge AI"


def test_brand_create_update_and_persistence(client, brand):
    assert brand["name"] == "Northstar Coffee"
    assert brand["colors"] == ["#C7FF2F", "#161616"]
    assert brand["business_description"] == "A small-batch coffee roaster."

    update = client.put(
        f"/api/brands/{brand['id']}",
        json={
            "name": "Northstar Coffee Roasters",
            "industry": "Specialty coffee",
            "description": "A small-batch coffee roaster.",
            "audience": "Home brewers who care about freshness.",
            "voice": "Warm, precise and unfussy.",
            "colors": ["#C7FF2F"],
            "contact": {"email": "hello@example.test", "phone": "+234 800 000 0000"},
            "social_links": {"Instagram": "https://instagram.com/northstar"},
            "preferred_platforms": ["Instagram", "TikTok"],
            "brand_guidelines": "Use plain language. Do not invent product claims.",
        },
    )
    assert update.status_code == 200, update.text
    assert update.json()["name"] == "Northstar Coffee Roasters"
    assert update.json()["contact"]["email"] == "hello@example.test"
    assert update.json()["social_links"]["Instagram"] == "https://instagram.com/northstar"
    assert update.json()["preferred_platforms"] == ["Instagram", "TikTok"]
    assert update.json()["brand_guidelines"] == "Use plain language. Do not invent product claims."

    # A fresh client must read the same SQLite record, not an in-memory copy.
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as second_client:
        listing = second_client.get("/api/brands")
    assert listing.status_code == 200
    names = [item["name"] for item in listing.json()["brands"]]
    assert "Northstar Coffee Roasters" in names


def test_brand_delete_keeps_project_and_clears_its_brand_link(client, brand, project):
    deleted = client.delete(f"/api/brands/{brand['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/brands/{brand['id']}").status_code == 404

    still_saved = client.get(f"/api/projects/{project['id']}")
    assert still_saved.status_code == 200
    assert still_saved.json()["brand_id"] is None


def test_project_create_update_delete(client, project, brand):
    assert project["name"] == "Autumn roast launch"
    assert project["brand_id"] == brand["id"]
    assert project["brand_name"] == "Northstar Coffee"

    update = client.put(
        f"/api/projects/{project['id']}",
        json={"name": "Autumn roast campaign", "status": "active", "description": "Updated brief."},
    )
    assert update.status_code == 200, update.text
    updated = update.json()
    assert updated["name"] == "Autumn roast campaign"
    assert updated["status"] == "active"
    assert updated["brand_id"] == brand["id"]

    listing = client.get("/api/projects")
    assert listing.status_code == 200
    assert any(item["id"] == project["id"] for item in listing.json()["projects"])

    deleted = client.delete(f"/api/projects/{project['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_free_only_settings_policy(client):
    paid = client.put("/api/settings", json={"openrouter_model": "anthropic/claude-3.5-sonnet"})
    assert paid.status_code == 400
    assert "Paid model rejected" in paid.json()["detail"]

    paid_gemini = client.put("/api/settings", json={"gemini_model": "gemini-4-argon"})
    assert paid_gemini.status_code == 400

    remote = client.put("/api/settings", json={"ollama_url": "http://example.com:11434"})
    assert remote.status_code == 422
    assert "localhost" in remote.json()["detail"].lower()

    unlock = client.put("/api/settings", json={"free_only": False})
    assert unlock.status_code == 400


def test_local_settings_save_and_reload(client):
    saved = client.put(
        "/api/settings",
        json={"ollama_model": "qwen2.5:1.5b", "theme": "light", "free_only": True},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["ollama_model"] == "qwen2.5:1.5b"
    assert saved.json()["theme"] == "light"
    assert saved.json()["free_only"] is True
    assert saved.json()["openrouter_configured"] is False
    assert saved.json()["gemini_configured"] is False
    assert saved.json()["groq_configured"] is False

    reloaded = client.get("/api/settings")
    assert reloaded.json()["ollama_model"] == "qwen2.5:1.5b"
    assert reloaded.json()["theme"] == "light"


def test_chat_context_serializes_local_project_and_brand_facts():
    brand = _brand_context({
        "name": "Northstar Coffee",
        "industry": "Food and beverage",
        "description": "A small-batch coffee roaster.",
        "products": "Whole-bean coffee.",
        "audience": "Home brewers.",
        "voice": "Warm and precise.",
        "guidelines": "Use plain language.",
        "website": "https://example.test",
        "colors": '["#C7FF2F"]',
        "platforms": '["Instagram", "TikTok"]',
    })
    project = _project_context({
        "name": "Autumn roast launch",
        "type": "general",
        "status": "draft",
        "description": "Introduce the new seasonal roast.",
    })
    assert "Northstar Coffee" in brand
    assert "Warm and precise." in brand
    assert "#C7FF2F" in brand
    assert "Instagram, TikTok" in brand
    assert "Autumn roast launch" in project
    assert "Introduce the new seasonal roast." in project


def test_local_selection_never_falls_through_to_cloud():
    chain = build_provider_chain({
        "ai_provider": "ollama",
        "ollama_model": "qwen2.5:1.5b",
        "openrouter_model": "vendor/model:free",
        "gemini_model": "gemini-2.5-flash",
        "groq_model": "openai/gpt-oss-20b",
        "openrouter_key_configured": True,
        "gemini_key_configured": True,
        "groq_key_configured": True,
        "provider_priority": ["openrouter", "gemini", "groq", "ollama"],
        "auto_fallback": True,
    })
    assert chain == ["ollama"]


def test_chat_validation(client):
    ends_with_assistant = client.post(
        "/api/ai/chat",
        json={"messages": [{"role": "assistant", "content": "Hello"}]},
    )
    assert ends_with_assistant.status_code == 422

    rewrite_without_selection = client.post(
        "/api/ai/chat",
        json={
            "messages": [{"role": "user", "content": "Rewrite this better."}],
            "mode": "rewrite",
        },
    )
    assert rewrite_without_selection.status_code == 422

    blank = client.post(
        "/api/ai/chat",
        json={"messages": [{"role": "user", "content": "   "}]},
    )
    assert blank.status_code == 422



def test_chat_request_limits_history_without_calling_a_model():
    with pytest.raises(ValidationError, match="Conversation history is too large"):
        ChatRequest(
            messages=[
                ChatMessage(role="assistant", content="a" * 9000),
                ChatMessage(role="user", content="b" * 9000),
                ChatMessage(role="assistant", content="c" * 9000),
                ChatMessage(role="user", content="continue"),
            ]
        )


def test_chat_reports_local_connection_failure_without_cloud_fallback(client):
    changed = client.put(
        "/api/settings",
        json={"ollama_url": "http://127.0.0.1:1", "ollama_model": "llama3.2:3b"},
    )
    assert changed.status_code == 200
    try:
        response = client.post(
            "/api/ai/chat",
            json={"messages": [{"role": "user", "content": "Give me one practical project next step."}]},
        )
    finally:
        client.put(
            "/api/settings",
            json={"ollama_url": "http://127.0.0.1:11434", "ollama_model": "llama3.2:3b"},
        )

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "provider_error_chain"
    assert "No paid fallback was attempted" in body["detail"]
    assert "Ollama is not reachable" in body["detail"]


def test_ollama_test_rejects_remote_urls(client):
    response = client.post(
        "/api/system/ollama/test",
        json={"base_url": "https://ollama.example.com", "model": "llama3.2:3b"},
    )
    assert response.status_code == 422, response.text
    assert "localhost" in response.json()["detail"]


def test_provider_helpers_reject_remote_urls_before_any_request():
    # This unit test does not use the TestClient fixture, so initialize its isolated SQLite schema
    # before provider settings are loaded.
    init_db()
    with pytest.raises(ProviderError) as models_error:
        asyncio.run(get_ollama_models("http://192.0.2.10:11434"))
    assert models_error.value.status_code == 422
    assert models_error.value.kind == "config"

    with pytest.raises(ProviderError) as chat_error:
        asyncio.run(
            _ollama_chat(
                prompt="Hello",
                system=None,
                model="llama3.2:3b",
                temperature=0,
                max_tokens=8,
                json_mode=False,
                base_url="https://ollama.example.com",
                operation="test",
            )
        )
    assert chat_error.value.status_code == 422
    assert "localhost" in str(chat_error.value)


def test_ollama_connection_check_lists_models_without_generating(client, monkeypatch):
    async def fake_models(base_url=None):
        return [{"name": "llama3.2:3b"}, {"name": "qwen2.5:1.5b"}]

    async def refuse_generation(*args, **kwargs):
        raise AssertionError("A connection check must not load or run a model")

    monkeypatch.setattr(providers, "get_ollama_models", fake_models)
    monkeypatch.setattr(providers, "_ollama_chat", refuse_generation)

    response = client.post(
        "/api/system/ollama/test",
        json={"base_url": "http://127.0.0.1:11434", "model": "llama3.2:3b"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    assert body["connection_check"] == "server_and_models"
    assert body["selected_model_available"] is True
    assert body["models"] == ["llama3.2:3b", "qwen2.5:1.5b"]
    assert "test_reply" not in body
