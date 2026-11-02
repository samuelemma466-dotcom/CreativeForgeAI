from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..config import FFMPEG, FFPROBE


class MediaProbeError(RuntimeError):
    pass


def _run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MediaProbeError(f"Required command not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError(f"Command timed out after {timeout}s: {command[0]}") from exc


def tool_version(command: str) -> str | None:
    try:
        result = subprocess.run(
            [command, "-version"], capture_output=True, text=True, timeout=10, check=False
        )
        first = (result.stdout or result.stderr).splitlines()
        return first[0].strip() if first else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def ffprobe(path: Path, timeout: int = 30) -> dict[str, Any]:
    result = _run(
        [
            FFPROBE,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=timeout,
    )
    if result.returncode != 0:
        message = (result.stderr or "Invalid or unreadable media file").strip()
        raise MediaProbeError(message[-600:])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError("FFprobe returned invalid JSON") from exc


def probe_info(path: Path) -> dict[str, Any]:
    payload = ffprobe(path)
    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = 0.0
    for candidate in (payload.get("format", {}).get("duration"), (video or {}).get("duration"), (audio or {}).get("duration")):
        try:
            duration = float(candidate)
            break
        except (TypeError, ValueError):
            continue
    width = int(video.get("width") or 0) if video else None
    height = int(video.get("height") or 0) if video else None
    return {
        "duration": round(max(0.0, duration), 3),
        "width": width,
        "height": height,
        "has_video": bool(video),
        "has_audio": bool(audio),
        "video_codec": (video or {}).get("codec_name"),
        "audio_codec": (audio or {}).get("codec_name"),
        "format_name": payload.get("format", {}).get("format_name"),
        "bit_rate": payload.get("format", {}).get("bit_rate"),
        "raw": payload,
    }


def extract_thumbnail(video: Path, output: Path, at: float = 0.15, width: int = 480) -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-ss",
            str(max(0.0, at)),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            "-q:v",
            "3",
            str(output),
        ],
        timeout=60,
    )
    return result.returncode == 0 and output.exists() and output.stat().st_size > 0
