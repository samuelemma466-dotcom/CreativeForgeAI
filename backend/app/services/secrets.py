from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from ..config import SECRETS_PATH, ensure_directories


def load_secrets() -> dict[str, Any]:
    ensure_directories()
    if not SECRETS_PATH.exists():
        return {}
    try:
        with SECRETS_PATH.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_secrets(secrets: dict[str, Any]) -> None:
    ensure_directories()
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=".secrets-", suffix=".json", dir=str(SECRETS_PATH.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(secrets, handle, indent=2)
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, SECRETS_PATH)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def get_secret(key: str) -> str | None:
    value = load_secrets().get(key)
    return value if isinstance(value, str) and value else None


def set_secret(key: str, value: str | None) -> None:
    secrets = load_secrets()
    if value:
        secrets[key] = value
    else:
        secrets.pop(key, None)
    save_secrets(secrets)


def masked_secret_status(key: str) -> bool:
    return bool(get_secret(key))
