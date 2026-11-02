from __future__ import annotations

import asyncio
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from ..config import APP_NAME, APP_VERSION, DATA_DIR, DB_PATH, MEDIA_ROOT, REPO_ROOT
from ..db import DB_PATH as DB_FILE, get_db, setting_get
from ..services.ffmpeg_tools import tool_version
from ..services.providers import (
    all_providers_status,
    build_provider_chain,
    get_provider_settings,
    ollama_status,
    provider_cooldown,
)
from ..services.secrets import masked_secret_status

router = APIRouter(prefix="/api", tags=["system"])


def _meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, raw = line.split(":", 1)
                if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                    values[key] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return values


def _directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _tools() -> tuple[dict[str, bool], dict[str, str | None]]:
    commands = {
        "ffmpeg": "ffmpeg",
        "ffprobe": "ffprobe",
        "espeak": "espeak-ng",
        "imagemagick": "magick",
        "ollama": "ollama",
    }
    available = {key: shutil.which(command) is not None for key, command in commands.items()}
    versions = {
        "ffmpeg": tool_version("ffmpeg") if available["ffmpeg"] else None,
        "ffprobe": tool_version("ffprobe") if available["ffprobe"] else None,
        "espeak": tool_version("espeak-ng") if available["espeak"] else None,
        "imagemagick": tool_version("magick") if available["imagemagick"] else None,
    }
    return available, versions


def _db_counts() -> dict[str, int]:
    with get_db() as db:
        brands = db.execute("SELECT COUNT(*) AS n FROM brands").fetchone()["n"]
        campaigns = db.execute("SELECT COUNT(*) AS n FROM campaigns").fetchone()["n"]
        projects = db.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
        design = db.execute("SELECT COUNT(*) AS n FROM projects WHERE type='design'").fetchone()["n"]
        video = db.execute("SELECT COUNT(*) AS n FROM projects WHERE type='video'").fetchone()["n"]
        media = db.execute("SELECT COUNT(*) AS n FROM media").fetchone()["n"]
        exports = db.execute("SELECT COUNT(*) AS n FROM exports").fetchone()["n"]
        completed = db.execute(
            "SELECT COUNT(*) AS n FROM exports WHERE status='completed'"
        ).fetchone()["n"]
        copy_items = db.execute("SELECT COUNT(*) AS n FROM copy_items").fetchone()["n"]
        subtitles = db.execute("SELECT COUNT(*) AS n FROM subtitles").fetchone()["n"]
        ai_requests = db.execute("SELECT COUNT(*) AS n FROM ai_usage").fetchone()["n"]
    return {
        "brands": brands,
        "campaigns": campaigns,
        "projects": projects,
        "design_projects": design,
        "video_projects": video,
        "media": media,
        "exports": exports,
        "completed_exports": completed,
        "copy_items": copy_items,
        "subtitles": subtitles,
        "ai_requests": ai_requests,
    }


@router.get("/health")
def health() -> dict:
    db_ok = True
    try:
        with get_db() as db:
            db.execute("SELECT 1").fetchone()
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": APP_NAME,
        "version": APP_VERSION,
        "database": "ok" if db_ok else "error",
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@router.get("/system/status")
async def system_status() -> dict:
    tools, versions = _tools()
    memory = _meminfo()
    disk = shutil.disk_usage(REPO_ROOT)
    try:
        ollama = await ollama_status()
    except Exception as exc:
        ollama = {
            "id": "ollama",
            "name": "Ollama (local)",
            "pricing": "local",
            "capabilities": ["text"],
            "available": False,
            "configured": False,
            "models": [],
            "error": str(exc),
            "free": True,
        }
    try:
        providers = await all_providers_status()
    except Exception:
        providers = [ollama]
    with get_db() as db:
        migrations = db.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]
        theme = setting_get(db, "theme", "dark") or "dark"
    return {
        "status": "ok",
        "version": APP_VERSION,
        "python_version": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "cpu": platform.processor() or "Unknown CPU",
        "cpu_count": os.cpu_count() or 0,
        "memory": {
            "total_bytes": memory.get("MemTotal", 0),
            "available_bytes": memory.get("MemAvailable", 0),
            "swap_total_bytes": memory.get("SwapTotal", 0),
            "swap_free_bytes": memory.get("SwapFree", 0),
        },
        "disk": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
        },
        "tools": tools,
        "tool_versions": versions,
        "ollama": ollama,
        "providers": providers,
        "free_only": True,
        "theme": theme,
        "storage": {
            "media_bytes": _directory_size(MEDIA_ROOT),
            "db_bytes": DB_FILE.stat().st_size if DB_FILE.exists() else 0,
            "free_bytes": disk.free,
            "total_bytes": disk.total,
        },
        "paths": {
            "repo": str(REPO_ROOT),
            "data": str(DATA_DIR),
            "media": str(MEDIA_ROOT),
            "database": str(DB_PATH),
            "secrets_configured": any(
                masked_secret_status(f"{provider}_api_key")
                for provider in ("openrouter", "gemini", "groq")
            ),
            "secrets": {
                provider: masked_secret_status(f"{provider}_api_key")
                for provider in ("openrouter", "gemini", "groq")
            },
        },
        "schema_version": migrations,
    }


@router.get("/dashboard")
async def dashboard() -> dict:
    counts = _db_counts()
    disk = shutil.disk_usage(REPO_ROOT)
    with get_db() as db:
        recent_projects = [
            dict(row)
            for row in db.execute(
                """
                SELECT p.id, p.type, p.name, p.description, p.status, p.brand_id,
                       p.thumbnail_path, p.created_at, p.updated_at, b.name AS brand_name
                FROM projects p LEFT JOIN brands b ON b.id = p.brand_id
                ORDER BY p.updated_at DESC LIMIT 6
                """
            ).fetchall()
        ]
        recent_campaigns = [
            dict(row)
            for row in db.execute(
                """
                SELECT c.id, c.name, c.platform, c.objective, c.status, c.generated_at,
                       c.created_at, c.updated_at, b.name AS brand_name
                FROM campaigns c LEFT JOIN brands b ON b.id = c.brand_id
                ORDER BY c.updated_at DESC LIMIT 5
                """
            ).fetchall()
        ]
        recent_exports = [
            dict(row)
            for row in db.execute(
                """
                SELECT e.id, e.project_id, e.type, e.format, e.status, e.progress,
                       e.error, e.created_at, e.completed_at, p.name AS project_name
                FROM exports e LEFT JOIN projects p ON p.id = e.project_id
                ORDER BY e.created_at DESC LIMIT 6
                """
            ).fetchall()
        ]
        recent_brands = [
            dict(row)
            for row in db.execute(
                "SELECT id, name, industry, colors, updated_at FROM brands ORDER BY updated_at DESC LIMIT 4"
            ).fetchall()
        ]
        ai_today = db.execute(
            "SELECT COUNT(*) AS n FROM ai_usage WHERE created_at >= ?",
            (datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00"),),
        ).fetchone()["n"]
    media_bytes = _directory_size(MEDIA_ROOT)
    settings = get_provider_settings()
    try:
        ollama = await asyncio.wait_for(ollama_status(), timeout=4)
        ollama_summary = {
            "available": ollama.get("available") and ollama.get("selected_model_available"),
            "model": ollama.get("model"),
            "error": ollama.get("error"),
        }
    except Exception:
        ollama_summary = {"available": False, "model": settings["ollama_model"], "error": "Ollama did not respond"}
    chain = build_provider_chain(settings)
    provider_summary = {
        "active": settings["ai_provider"],
        "chain": chain,
        "auto_fallback": settings["auto_fallback"],
        "ollama": ollama_summary,
        "openrouter": {
            "configured": settings["openrouter_key_configured"],
            "model": settings["openrouter_model"] or None,
            "cooldown_seconds": provider_cooldown("openrouter"),
            "note": "Free models only. Optional.",
        },
        "gemini": {
            "configured": settings["gemini_key_configured"],
            "model": settings["gemini_model"],
            "cooldown_seconds": provider_cooldown("gemini"),
            "note": "Free-tier text models only. Optional.",
        },
        "groq": {
            "configured": settings["groq_key_configured"],
            "model": settings["groq_model"],
            "cooldown_seconds": provider_cooldown("groq"),
            "note": "Free-plan text models only. Optional.",
        },
        "free_only": True,
    }
    return {
        "counts": counts,
        "recent_projects": [
            {
                "id": row["id"],
                "type": row["type"],
                "name": row["name"],
                "description": row["description"],
                "status": row["status"],
                "brand_id": row["brand_id"],
                "brand_name": row["brand_name"],
                "thumbnail_url": f"/api/projects/{row['id']}/thumbnail" if row["thumbnail_path"] else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in recent_projects
        ],
        "recent_campaigns": [
            {
                **row,
                "brand_name": row["brand_name"],
            }
            for row in recent_campaigns
        ],
        "recent_exports": [
            {
                **{key: value for key, value in row.items() if key != "progress"},
                "file_url": f"/api/exports/{row['id']}/file" if row["status"] == "completed" else None,
            }
            for row in recent_exports
        ],
        "recent_brands": recent_brands,
        "storage": {
            "media_bytes": media_bytes,
            "db_bytes": DB_FILE.stat().st_size if DB_FILE.exists() else 0,
            "free_bytes": disk.free,
            "total_bytes": disk.total,
            "used_bytes": disk.used,
        },
        "providers": provider_summary,
        "ai_requests_today": ai_today,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "free_only": True,
    }
