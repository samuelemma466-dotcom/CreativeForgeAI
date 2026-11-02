from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from ..config import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MAX_AUDIO_BYTES,
    MAX_IMAGE_BYTES,
    MAX_VIDEO_BYTES,
    MEDIA_ROOT,
    UPLOAD_DIR,
    VIDEO_EXTENSIONS,
    VOICE_DIR,
    PROJECT_MEDIA_DIR,
)
from ..db import get_db, utc_now
from ..utils.security import ensure_within, is_within, media_path, safe_filename
from .ffmpeg_tools import MediaProbeError, probe_info

Image.MAX_IMAGE_PIXELS = 45_000_000
CHUNK_SIZE = 1024 * 1024


class MediaValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _kind_for_extension(extension: str) -> tuple[str, int]:
    if extension in IMAGE_EXTENSIONS:
        return "image", MAX_IMAGE_BYTES
    if extension in AUDIO_EXTENSIONS:
        return "audio", MAX_AUDIO_BYTES
    if extension in VIDEO_EXTENSIONS:
        return "video", MAX_VIDEO_BYTES
    raise MediaValidationError(
        "Unsupported file type. Use images (png/jpg/webp), audio (mp3/wav/m4a/aac/ogg/flac) "
        "or video (mp4/mov/webm/mkv/m4v).",
        status_code=415,
    )


def _inspect_image(path: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
        if width < 1 or height < 1:
            raise MediaValidationError("Image has invalid dimensions")
        if width * height > 45_000_000:
            raise MediaValidationError("Image resolution is too large")
        return width, height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise MediaValidationError("File is not a valid image") from exc


async def store_upload(upload: UploadFile, kind_hint: str | None = None) -> dict:
    original_name = safe_filename(upload.filename or "upload")
    extension = Path(original_name).suffix.lower()
    kind, max_bytes = _kind_for_extension(extension)
    if kind_hint and kind_hint in {"image", "audio", "video"} and kind_hint != kind:
        raise MediaValidationError(f"File extension does not match requested {kind_hint} upload type")

    now = datetime.now(timezone.utc)
    folder = UPLOAD_DIR / f"{now.year:04d}" / f"{now.month:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    destination = folder / stored_name
    size = 0
    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise MediaValidationError(
                        f"File exceeds the {max_bytes // (1024 * 1024)} MB limit",
                        status_code=413,
                    )
                handle.write(chunk)
        if size == 0:
            raise MediaValidationError("Uploaded file is empty")

        width = height = None
        duration = None
        if kind == "image":
            width, height = _inspect_image(destination)
        else:
            try:
                info = probe_info(destination)
            except MediaProbeError as exc:
                raise MediaValidationError(f"File is not valid {kind}: {exc}") from exc
            if kind == "video" and not info["has_video"]:
                raise MediaValidationError("File does not contain a video stream")
            if kind == "audio" and not info["has_audio"]:
                raise MediaValidationError("File does not contain an audio stream")
            duration = info["duration"] or None
            width = info["width"] if kind == "video" else None
            height = info["height"] if kind == "video" else None

        relative = destination.resolve().relative_to(MEDIA_ROOT.resolve()).as_posix()
        mime_type = mimetypes.guess_type(original_name)[0] or upload.content_type or "application/octet-stream"
        media_id = uuid4().hex
        with get_db() as db:
            db.execute(
                """
                INSERT INTO media
                    (id, original_name, stored_name, relative_path, mime_type, kind,
                     size_bytes, width, height, duration, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    media_id,
                    original_name,
                    stored_name,
                    relative,
                    mime_type,
                    kind,
                    size,
                    width,
                    height,
                    duration,
                    utc_now(),
                ),
            )
            row = db.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
        return dict(row)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def get_media(media_id: str) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
    return dict(row) if row else None


def list_media(kind: str | None = None, limit: int = 500) -> list[dict]:
    with get_db() as db:
        if kind:
            rows = db.execute(
                "SELECT * FROM media WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM media ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(row) for row in rows]


def media_file(media: dict) -> Path:
    path = media_path(media["relative_path"])
    if not path.exists() or not path.is_file():
        raise MediaValidationError("Media file is missing from local storage", status_code=404)
    # Voice and project-generated media are stored inside media/, uploads are immutable.
    ensure_within(path, MEDIA_ROOT)
    return path


def delete_media(media_id: str) -> bool:
    media = get_media(media_id)
    if not media:
        return False
    path = media_path(media["relative_path"])
    with get_db() as db:
        db.execute("DELETE FROM media WHERE id = ?", (media_id,))
    if path.exists():
        # Only originals/voice files are removed. Never touch exports.
        if is_within(path, UPLOAD_DIR) or is_within(path, VOICE_DIR) or is_within(path, PROJECT_MEDIA_DIR):
            path.unlink(missing_ok=True)
    return True
