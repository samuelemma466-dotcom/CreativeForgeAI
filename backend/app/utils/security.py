from __future__ import annotations

import re
from pathlib import Path


def safe_filename(name: str, fallback: str = "file") -> str:
    base = Path(name or fallback).name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" ._")
    return cleaned[:180] or fallback


def ensure_within(path: Path, root: Path) -> Path:
    """Resolve a path and guarantee it stays inside root (no traversal/symlink escape)."""
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError("Path escapes the allowed storage root")
    return resolved


def is_within(path: Path, root: Path) -> bool:
    try:
        ensure_within(path, root)
        return True
    except ValueError:
        return False


def relative_to_media(path: Path) -> str:
    from ..config import MEDIA_ROOT

    return ensure_within(path, MEDIA_ROOT).relative_to(MEDIA_ROOT.resolve()).as_posix()


def media_path(relative_path: str) -> Path:
    from ..config import MEDIA_ROOT

    candidate = MEDIA_ROOT / relative_path
    return ensure_within(candidate, MEDIA_ROOT)


def ffmpeg_filter_escape(value: str) -> str:
    """Escape a value used inside an FFmpeg filter option."""
    return (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(";", "\\;")
    )
