from __future__ import annotations

import mimetypes
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from ..config import ESPEAK, VOICE_DIR
from ..db import get_db, utc_now
from ..schemas import VoiceRequest
from ..utils.security import relative_to_media
from .ffmpeg_tools import MediaProbeError, probe_info
from .media import MediaValidationError


def list_voices() -> list[dict]:
    try:
        result = subprocess.run(
            [ESPEAK, "--voices"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaValidationError(f"eSpeak NG is unavailable: {exc}", status_code=503) from exc
    if result.returncode != 0:
        raise MediaValidationError(
            (result.stderr or "eSpeak NG could not list voices").strip(), status_code=503
        )
    voices: list[dict] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 4:
            continue
        head = parts[0].split()
        if len(head) < 2 or not head[0].isdigit():
            continue
        voice_id = head[-1]
        if voice_id in seen:
            continue
        age_gender = parts[1]
        gender = "unknown"
        if "/" in age_gender:
            gender = age_gender.split("/")[-1]
        voices.append(
            {
                "id": voice_id,
                "language": re.sub(r"[+-].*$", "", voice_id),
                "variant": voice_id,
                "gender": gender,
                "name": parts[2],
                "file": parts[3] if len(parts) > 3 else voice_id,
            }
        )
        seen.add(voice_id)
    return sorted(voices, key=lambda item: (item["language"], item["id"]))


def generate_voice(request: VoiceRequest) -> dict:
    if "\x00" in request.text:
        raise MediaValidationError("Voiceover text contains invalid characters")
    if not re.match(r"^[A-Za-z0-9_+\-]+$", request.voice):
        raise MediaValidationError("Invalid voice identifier")
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"voice-{uuid4().hex}.wav"
    output = VOICE_DIR / filename
    command = [
        ESPEAK,
        "-v",
        request.voice,
        "-s",
        str(request.rate),
        "-p",
        str(request.pitch),
        "-w",
        str(output),
        "--",
        request.text,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except FileNotFoundError as exc:
        raise MediaValidationError(
            "eSpeak NG is not installed. Install espeak-ng with your system package manager.",
            status_code=503,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        output.unlink(missing_ok=True)
        raise MediaValidationError("Voice generation timed out", status_code=504) from exc
    if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        message = (result.stderr or "eSpeak NG failed to generate audio").strip()
        raise MediaValidationError(message[-500:], status_code=500)
    try:
        info = probe_info(output)
    except MediaProbeError as exc:
        output.unlink(missing_ok=True)
        raise MediaValidationError(f"Generated audio failed validation: {exc}", status_code=500) from exc
    media_id = uuid4().hex
    title = (request.title or request.text[:60]).strip() or "Voiceover"
    with get_db() as db:
        db.execute(
            """
            INSERT INTO media
                (id, original_name, stored_name, relative_path, mime_type, kind,
                 size_bytes, width, height, duration, created_at)
            VALUES (?, ?, ?, ?, ?, 'audio', ?, NULL, NULL, ?, ?)
            """,
            (
                media_id,
                f"{title[:120]}.wav",
                filename,
                relative_to_media(output),
                mimetypes.guess_type(filename)[0] or "audio/wav",
                output.stat().st_size,
                info["duration"] or None,
                utc_now(),
            ),
        )
        row = db.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
    return dict(row)
