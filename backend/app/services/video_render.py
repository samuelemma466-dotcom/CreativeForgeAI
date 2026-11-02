from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Callable

from ..config import FFMPEG, FONTS, TEMP_DIR
from ..db import get_db
from ..schemas import VideoData, VideoClip
from ..utils.security import ensure_within, ffmpeg_filter_escape
from .ffmpeg_tools import MediaProbeError, probe_info
from .media import get_media, media_file
from .subtitles import SrtError, normalize_srt


class VideoRenderError(RuntimeError):
    pass


class RenderCancelled(VideoRenderError):
    pass


def _even(value: float) -> int:
    return max(2, int(round(value / 2.0)) * 2)


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _hex_rgb(value: str) -> tuple[int, int, int]:
    cleaned = value.strip().lstrip("#")
    if len(cleaned) == 8:
        cleaned = cleaned[:6]
    if len(cleaned) != 6:
        return (255, 255, 255)
    return tuple(int(cleaned[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _drawtext_color(value: str) -> tuple[str, float]:
    cleaned = value.strip().lstrip("#")
    alpha = 1.0
    if len(cleaned) == 8:
        alpha = int(cleaned[6:8], 16) / 255
        cleaned = cleaned[:6]
    return f"0x{cleaned.upper()}", alpha


def _ass_color(value: str) -> str:
    red, green, blue = _hex_rgb(value)
    return f"&H00{blue:02X}{green:02X}{red:02X}&"


def _font_path(bold: bool) -> Path:
    key = "sans_bold" if bold else "sans"
    path = FONTS.get(key) or FONTS["sans"]
    return path if path.exists() else FONTS["sans"]


def _text_wrap(text: str, font_size: int, max_width: int) -> str:
    # drawtext does not wrap automatically. Approximate average glyph width and wrap.
    max_chars = max(10, int(max_width / max(font_size * 0.52, 1)))
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        lines.extend(
            textwrap.wrap(
                paragraph,
                width=max_chars,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
        )
    return "\n".join(lines)


def _position(clip: VideoClip, output_w: int, output_h: int) -> tuple[str, str]:
    style = clip.style
    if style.position == "top":
        return "(w-text_w)/2", f"{_num(output_h * 0.075)}"
    if style.position == "center":
        return "(w-text_w)/2", "(h-text_h)/2"
    if style.position == "lower_third":
        return f"{_num(output_w * 0.07)}", f"{_num(output_h * 0.70)}"
    if style.position == "custom":
        return (
            f"(w-text_w)*{_num(style.x_pct)}/100",
            f"(h-text_h)*{_num(style.y_pct)}/100",
        )
    return "(w-text_w)/2", f"h-text_h-{_num(output_h * 0.075)}"


def _motion_filter(clip: VideoClip, width: int, height: int, fps: int) -> str:
    frames = max(1, int(round(clip.duration * fps)))
    if clip.motion == "none":
        return ""
    zoom = "min(1+0.18*on/{frames},1.18)" if clip.motion == "zoom_in" else "max(1.18-0.18*on/{frames},1.0)"
    if clip.motion in {"zoom_in", "zoom_out"}:
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif clip.motion == "pan_left":
        zoom = "1.12"
        x_expr = f"(iw-iw/zoom)*(1-on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        zoom = "1.12"
        x_expr = f"(iw-iw/zoom)*(on/{frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    zoom = zoom.format(frames=frames)
    return (
        f"scale={int(width * 1.2)}:{int(height * 1.2)}:force_original_aspect_ratio=increase,"
        f"crop={int(width * 1.2)}:{int(height * 1.2)},"
        f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps},"
        f"trim=duration={_num(clip.duration)},setpts=PTS-STARTPTS"
    )


def _clip_visual_chain(
    clip: VideoClip,
    media: dict,
    width: int,
    height: int,
    fps: int,
    background: str,
) -> str:
    chain: list[str] = []
    if clip.rotation == 90:
        chain.append("transpose=1")
    elif clip.rotation == 180:
        chain.append("transpose=2,transpose=2")
    elif clip.rotation == 270:
        chain.append("transpose=2")
    chain.append(f"trim=duration={_num(clip.duration)},setpts=PTS-STARTPTS")
    if clip.kind == "image" and clip.motion != "none":
        chain.append(_motion_filter(clip, width, height, fps))
    else:
        if clip.fit == "contain":
            r, g, b = _hex_rgb(background)
            chain.append(
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x{r:02X}{g:02X}{b:02X}"
            )
        else:
            chain.append(
                f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
            )
        chain.append(f"fps={fps}")
    chain.append("setsar=1")
    fade_in = clip.fade_in
    fade_out = clip.fade_out
    if clip.transition == "fade":
        fade_in = fade_in or 0.4
        fade_out = fade_out or 0.4
    if fade_in > 0:
        chain.append(f"fade=t=in:st=0:d={_num(min(fade_in, clip.duration))}")
    if fade_out > 0:
        start = max(0.0, clip.duration - min(fade_out, clip.duration))
        chain.append(f"fade=t=out:st={_num(start)}:d={_num(min(fade_out, clip.duration))}")
    chain.append(f"setpts=PTS-STARTPTS+{_num(clip.start)}/TB")
    return ",".join(chain)


def _text_filter(clip: VideoClip, output_w: int, output_h: int, project_height: int, temp: Path, index: int) -> tuple[str, Path]:
    style = clip.style
    scale_y = output_h / max(1, project_height)
    font_size = max(10, round(style.font_size * scale_y))
    max_width = int(output_w * style.max_width_pct / 100)
    wrapped = _text_wrap(clip.text, font_size, max_width)
    text_path = temp / f"text-{index}.txt"
    text_path.write_text(wrapped, encoding="utf-8")
    color, alpha = _drawtext_color(style.color)
    fontfile = ffmpeg_filter_escape(str(_font_path(style.bold)))
    textfile = ffmpeg_filter_escape(str(text_path))
    x_expr, y_expr = _position(clip, output_w, output_h)
    parts = [
        f"fontfile='{fontfile}'",
        f"textfile='{textfile}'",
        "expansion=none",
        f"fontsize={font_size}",
        f"fontcolor={color}@{_num(alpha)}",
        f"x={x_expr}",
        f"y={y_expr}",
        f"enable='between(t,{_num(clip.start)},{_num(clip.start + clip.duration)})'",
    ]
    if style.background_opacity > 0:
        box_color, box_alpha = _drawtext_color(style.background_color)
        alpha_total = max(0.0, min(1.0, box_alpha * style.background_opacity))
        parts.extend(
            [
                "box=1",
                f"boxcolor={box_color}@{_num(alpha_total)}",
                f"boxborderw={max(6, round(font_size * 0.28))}",
            ]
        )
    if style.shadow:
        parts.extend(
            [
                "shadowcolor=black@0.55",
                f"shadowx={max(1, round(scale_y * 2))}",
                f"shadowy={max(1, round(scale_y * 2))}",
            ]
        )
    return "drawtext=" + ":".join(parts), text_path


def _subtitle_filter(
    project_id: str,
    data: VideoData,
    output_w: int,
    output_h: int,
    temp: Path,
) -> str | None:
    if not data.subtitles.enabled:
        return None
    subtitle = None
    with get_db() as db:
        if data.subtitle_id:
            row = db.execute("SELECT * FROM subtitles WHERE id = ?", (data.subtitle_id,)).fetchone()
            subtitle = dict(row) if row else None
        if not subtitle:
            row = db.execute(
                "SELECT * FROM subtitles WHERE project_id = ? ORDER BY updated_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            subtitle = dict(row) if row else None
    if not subtitle or not subtitle.get("srt", "").strip():
        raise VideoRenderError(
            "Subtitles are enabled but this video has no subtitle content. Add subtitles or disable them."
        )
    try:
        normalized = normalize_srt(subtitle["srt"])
    except SrtError as exc:
        raise VideoRenderError(f"Subtitle file is invalid: {exc}") from exc
    if not normalized.strip():
        return None
    subtitle_path = temp / "subtitles.srt"
    subtitle_path.write_text(normalized, encoding="utf-8")
    style = data.subtitles
    font_size = max(12, round(style.font_size * output_h / max(1, data.height)))
    margin = max(0, round(style.margin_v * output_h / max(1, data.height)))
    alignment = {"bottom": 2, "center": 5, "top": 8}[style.position]
    force_style = (
        f"FontName=Liberation Sans,FontSize={font_size},"
        f"PrimaryColour={_ass_color(style.color)},"
        f"OutlineColour={_ass_color(style.outline_color)},"
        f"Outline={style.outline},Alignment={alignment},MarginV={margin}"
    )
    path = ffmpeg_filter_escape(str(subtitle_path))
    return f"subtitles=filename='{path}':force_style='{force_style}'"


def _audio_filter(clip: VideoClip, input_index: int) -> str | None:
    if clip.muted or clip.volume <= 0:
        return None
    duration = clip.duration
    parts = [
        f"atrim=0:{_num(duration)}",
        "asetpts=PTS-STARTPTS",
        "aresample=48000",
        "aformat=sample_fmts=fltp:channel_layouts=stereo",
        f"volume={_num(clip.volume)}",
    ]
    if clip.fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={_num(min(clip.fade_in, duration))}")
    if clip.fade_out > 0:
        start = max(0.0, duration - min(clip.fade_out, duration))
        parts.append(f"afade=t=out:st={_num(start)}:d={_num(min(clip.fade_out, duration))}")
    parts.append(f"adelay={max(0, round(clip.start * 1000))}:all=1")
    return f"[{input_index}:a]" + ",".join(parts) + f"[a{input_index}]"


def render_video(
    project: dict[str, Any],
    data: VideoData | dict[str, Any],
    output_path: Path,
    *,
    mode: str = "export",
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
    crf: int = 23,
    max_width: int = 640,
    progress: Callable[[float], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not isinstance(data, VideoData):
        data = VideoData.model_validate(data)
    total_duration = data.duration()
    if total_duration <= 0.1:
        raise VideoRenderError("The timeline is empty. Add at least one clip before rendering.")
    if total_duration > 3600:
        raise VideoRenderError("Timeline is longer than the 60 minute limit")
    visual_clips = sorted(
        [
            clip
            for track in data.tracks
            if track.type == "visual"
            for clip in track.clips
            if clip.kind in {"video", "image"}
        ],
        key=lambda clip: (clip.start, clip.id),
    )
    if not visual_clips:
        raise VideoRenderError("Add at least one video or image clip before rendering.")

    text_clips = sorted(
        [clip for track in data.tracks if track.type == "text" for clip in track.clips if clip.kind == "text"],
        key=lambda clip: (clip.start, clip.id),
    )
    audio_clips = sorted(
        [
            clip
            for track in data.tracks
            if track.type == "audio"
            for clip in track.clips
            if clip.kind in {"audio", "voice", "music"} and not clip.muted
        ],
        key=lambda clip: (clip.start, clip.id),
    )

    if mode == "preview":
        target_width = min(max(320, max_width), data.width)
        ratio = target_width / data.width
        out_w = _even(target_width)
        out_h = _even(data.height * ratio)
        out_fps = min(24, data.fps)
        preset = "ultrafast"
        crf = 31
        audio_bitrate = "128k"
    else:
        out_w = _even(width or data.width)
        out_h = _even(height or data.height)
        out_fps = fps or data.fps
        preset = "veryfast"
        audio_bitrate = "192k"

    temp = Path(tempfile.mkdtemp(prefix="cfai-render-", dir=str(TEMP_DIR)))
    command: list[str] = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-progress",
        "pipe:1",
        "-nostats",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x{''.join(f'{v:02X}' for v in _hex_rgb(data.background))}:s={out_w}x{out_h}:r={out_fps}:d={_num(total_duration)}",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
    ]
    next_input = 2
    visual_inputs: list[tuple[VideoClip, int, dict]] = []
    for clip in visual_clips:
        media = get_media(clip.media_id or "")
        if not media:
            raise VideoRenderError(f"Missing media for clip '{clip.label or clip.id}'")
        try:
            path = media_file(media)
        except Exception as exc:
            raise VideoRenderError(f"Media file is missing for clip '{clip.label or clip.id}'") from exc
        if clip.kind == "image" and media["kind"] != "image":
            raise VideoRenderError(f"Clip '{clip.label or clip.id}' expects an image asset")
        if clip.kind == "video" and media["kind"] != "video":
            raise VideoRenderError(f"Clip '{clip.label or clip.id}' expects a video asset")
        if clip.kind == "video":
            command.extend(["-ss", _num(clip.source_in), "-t", _num(clip.duration), "-i", str(path)])
        else:
            command.extend(["-loop", "1", "-framerate", str(out_fps), "-t", _num(clip.duration), "-i", str(path)])
        visual_inputs.append((clip, next_input, media))
        next_input += 1

    audio_inputs: list[tuple[VideoClip, int, dict]] = []
    for clip in audio_clips:
        media = get_media(clip.media_id or "")
        if not media:
            raise VideoRenderError(f"Missing audio for clip '{clip.label or clip.id}'")
        if media["kind"] != "audio":
            raise VideoRenderError(f"Clip '{clip.label or clip.id}' expects an audio asset")
        try:
            path = media_file(media)
        except Exception as exc:
            raise VideoRenderError(f"Audio file is missing for clip '{clip.label or clip.id}'") from exc
        command.extend(
            [
                "-ss",
                _num(clip.source_in),
                "-t",
                _num(clip.duration),
                "-vn",
                "-i",
                str(path),
            ]
        )
        audio_inputs.append((clip, next_input, media))
        next_input += 1

    graph: list[str] = []
    background_hex = "".join(f"{v:02X}" for v in _hex_rgb(data.background))
    graph.append(
        f"[0:v]format=yuv420p[basev]"
    )
    graph.append(
        f"[1:a]atrim=0:{_num(total_duration)},asetpts=PTS-STARTPTS,"
        f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[basea]"
    )
    current_video = "basev"
    for index, (clip, input_index, media) in enumerate(visual_inputs):
        chain = _clip_visual_chain(clip, media, out_w, out_h, out_fps, data.background)
        graph.append(f"[{input_index}:v]{chain}[vclip{index}]")
        graph.append(
            f"[{current_video}][vclip{index}]overlay="
            f"enable='between(t,{_num(clip.start)},{_num(clip.start + clip.duration)})':"
            f"eof_action=pass:repeatlast=0:format=auto[vover{index}]"
        )
        current_video = f"vover{index}"

    for index, clip in enumerate(text_clips):
        filter_text, _ = _text_filter(clip, out_w, out_h, data.height, temp, index)
        graph.append(f"[{current_video}]{filter_text}[vtext{index}]")
        current_video = f"vtext{index}"

    subtitle_filter = _subtitle_filter(project["id"], data, out_w, out_h, temp)
    if subtitle_filter:
        graph.append(f"[{current_video}]{subtitle_filter}[vsub]")
        current_video = "vsub"

    graph.append(f"[{current_video}]null[vout]")

    mix_inputs = ["basea"]
    for index, (clip, input_index, media) in enumerate(audio_inputs):
        audio_chain = _audio_filter(clip, input_index)
        if audio_chain:
            graph.append(audio_chain)
            mix_inputs.append(f"a{input_index}")
    if len(mix_inputs) == 1:
        graph.append("[basea]anull[aout]")
    else:
        graph.append(
            "".join(f"[{label}]" for label in mix_inputs)
            + f"amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0:normalize=0,"
            "alimiter=limit=0.95[aout]"
        )

    filter_script = temp / "filter_complex.txt"
    filter_script.write_text(";\n".join(graph), encoding="utf-8")
    command.extend(
        [
            "-filter_complex_script",
            str(filter_script),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-t",
            _num(total_duration),
            "-r",
            str(out_fps),
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            audio_bitrate,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-max_muxing_queue_size",
            "2048",
            str(output_path),
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path = temp / "ffmpeg-stderr.log"
    started = time.monotonic()
    try:
        with stderr_path.open("w", encoding="utf-8") as stderr_file:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
                text=True,
            )
            assert process.stdout is not None
            last_report = 0.0
            for line in process.stdout:
                if cancel_check and cancel_check():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise RenderCancelled("Render cancelled")
                line = line.strip()
                if line.startswith("out_time_ms=") or line.startswith("out_time_us="):
                    try:
                        microseconds = int(line.split("=", 1)[1])
                        seconds = microseconds / 1_000_000
                        if progress and time.monotonic() - last_report >= 0.8:
                            progress(max(0.0, min(99.0, seconds / total_duration * 100)))
                            last_report = time.monotonic()
                    except ValueError:
                        pass
                elif line.startswith("progress=end") and progress:
                    progress(99.0)
            return_code = process.wait()
    finally:
        pass
    if cancel_check and cancel_check():
        output_path.unlink(missing_ok=True)
        raise RenderCancelled("Render cancelled")
    if return_code != 0 or not output_path.exists() or output_path.stat().st_size < 1000:
        detail = ""
        try:
            detail = stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:].strip()
        except OSError:
            pass
        output_path.unlink(missing_ok=True)
        raise VideoRenderError(
            "FFmpeg could not render this timeline."
            + (f" Details: {detail}" if detail else "")
        )
    try:
        info = probe_info(output_path)
    except MediaProbeError as exc:
        output_path.unlink(missing_ok=True)
        raise VideoRenderError(f"Rendered file failed FFprobe validation: {exc}") from exc
    if not info["has_video"] or info["duration"] < 0.2:
        output_path.unlink(missing_ok=True)
        raise VideoRenderError("Rendered file is not a valid video according to FFprobe")
    if progress:
        progress(100.0)
    return {
        "width": info.get("width") or out_w,
        "height": info.get("height") or out_h,
        "duration": info["duration"],
        "fps": out_fps,
        "size_bytes": output_path.stat().st_size,
        "video_codec": info.get("video_codec"),
        "audio_codec": info.get("audio_codec"),
        "has_audio": info.get("has_audio"),
        "valid": True,
        "render_seconds": round(time.monotonic() - started, 2),
    }
