from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import DB_PATH, ensure_directories, utc_now


MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS brands (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            industry TEXT NOT NULL DEFAULT '',
            products TEXT NOT NULL DEFAULT '',
            audience TEXT NOT NULL DEFAULT '',
            voice TEXT NOT NULL DEFAULT '',
            colors TEXT NOT NULL DEFAULT '[]',
            logo_media_id TEXT REFERENCES media(id) ON DELETE SET NULL,
            contact TEXT NOT NULL DEFAULT '{}',
            website TEXT NOT NULL DEFAULT '',
            socials TEXT NOT NULL DEFAULT '{}',
            platforms TEXT NOT NULL DEFAULT '[]',
            guidelines TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            brand_id TEXT REFERENCES brands(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            product TEXT NOT NULL DEFAULT '',
            audience TEXT NOT NULL DEFAULT '',
            objective TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '',
            duration TEXT NOT NULL DEFAULT '',
            budget TEXT NOT NULL DEFAULT '',
            offer TEXT NOT NULL DEFAULT '',
            problem TEXT NOT NULL DEFAULT '',
            cta TEXT NOT NULL DEFAULT '',
            instructions TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            strategy TEXT NOT NULL DEFAULT '{}',
            generated_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS copy_items (
            id TEXT PRIMARY KEY,
            campaign_id TEXT REFERENCES campaigns(id) ON DELETE SET NULL,
            brand_id TEXT REFERENCES brands(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            tone TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL CHECK (type IN ('design', 'video', 'general')),
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            brand_id TEXT REFERENCES brands(id) ON DELETE SET NULL,
            campaign_id TEXT REFERENCES campaigns(id) ON DELETE SET NULL,
            data TEXT NOT NULL DEFAULT '{}',
            thumbnail_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS media (
            id TEXT PRIMARY KEY,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            relative_path TEXT NOT NULL UNIQUE,
            mime_type TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('image', 'audio', 'video')),
            size_bytes INTEGER NOT NULL,
            width INTEGER,
            height INTEGER,
            duration REAL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS exports (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
            type TEXT NOT NULL,
            format TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            progress REAL NOT NULL DEFAULT 0,
            output_path TEXT,
            settings TEXT NOT NULL DEFAULT '{}',
            probe TEXT NOT NULL DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ai_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            operation TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            duration_ms INTEGER,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subtitles (
            id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            srt TEXT NOT NULL DEFAULT '',
            style TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_campaigns_brand ON campaigns(brand_id);
        CREATE INDEX IF NOT EXISTS idx_copy_campaign ON copy_items(campaign_id);
        CREATE INDEX IF NOT EXISTS idx_projects_type ON projects(type);
        CREATE INDEX IF NOT EXISTS idx_projects_brand ON projects(brand_id);
        CREATE INDEX IF NOT EXISTS idx_media_kind ON media(kind);
        CREATE INDEX IF NOT EXISTS idx_exports_project ON exports(project_id);
        CREATE INDEX IF NOT EXISTS idx_exports_type ON exports(type);
        CREATE INDEX IF NOT EXISTS idx_subtitles_project ON subtitles(project_id);
        CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage(created_at);
        """,
    ),
]


def connect() -> sqlite3.Connection:
    ensure_directories()
    connection = sqlite3.connect(str(DB_PATH), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    ensure_directories()
    with get_db() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            row["version"]
            for row in db.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for version, script in MIGRATIONS:
            if version in applied:
                continue
            db.executescript(script)
            db.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, utc_now()),
            )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def setting_get(db: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def setting_set(db: sqlite3.Connection, key: str, value: str) -> None:
    db.execute(
        """
        INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, utc_now()),
    )
