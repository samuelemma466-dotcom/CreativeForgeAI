from __future__ import annotations

import re
from typing import Any

from ..schemas import SubtitleCreate, SubtitleUpdate

TIMESTAMP_RE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)


class SrtError(ValueError):
    pass


def _parse_timestamp(value: str) -> float:
    normalized = value.replace(".", ",")
    hours, minutes, rest = normalized.split(":")
    seconds, milliseconds = rest.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds.ljust(3, "0")[:3]) / 1000
    )


def parse_srt(srt: str) -> list[dict[str, Any]]:
    if not srt.strip():
        return []
    normalized = srt.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n{2,}", normalized)
    cues: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        lines = [line for line in block.split("\n")]
        if not lines:
            continue
        timestamp_index = 0
        if re.fullmatch(r"\d+", lines[0].strip()):
            timestamp_index = 1
        if timestamp_index >= len(lines):
            raise SrtError(f"Subtitle block {index} is missing a timestamp line")
        match = TIMESTAMP_RE.match(lines[timestamp_index].strip())
        if not match:
            raise SrtError(
                f"Subtitle block {index} has an invalid timestamp. Use HH:MM:SS,mmm --> HH:MM:SS,mmm"
            )
        start = _parse_timestamp(match.group("start"))
        end = _parse_timestamp(match.group("end"))
        if end <= start:
            raise SrtError(f"Subtitle block {index} ends before it starts")
        text = "\n".join(lines[timestamp_index + 1 :]).strip()
        if not text:
            raise SrtError(f"Subtitle block {index} has no text")
        cues.append({"index": len(cues) + 1, "start": start, "end": end, "text": text})
    if len(cues) > 2000:
        raise SrtError("Subtitle file has too many cues (maximum 2000)")
    return cues


def validate_srt(srt: str) -> dict[str, Any]:
    cues = parse_srt(srt)
    return {"cues": cues, "count": len(cues), "valid": True}


def normalize_srt(srt: str) -> str:
    cues = parse_srt(srt)
    if not cues:
        return ""
    blocks = []
    for cue in cues:
        blocks.append(
            f"{cue['index']}\n{format_timestamp(cue['start'])} --> {format_timestamp(cue['end'])}\n{cue['text']}"
        )
    return "\n\n".join(blocks) + "\n"


def format_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
