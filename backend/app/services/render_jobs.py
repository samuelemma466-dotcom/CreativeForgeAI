from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..config import EXPORT_DIR, PREVIEW_DIR, PROJECT_MEDIA_DIR
from ..db import get_db, utc_now
from ..schemas import VideoData
from ..utils.security import relative_to_media
from .ffmpeg_tools import extract_thumbnail
from .serializers import export_out
from .video_render import RenderCancelled, VideoRenderError, render_video

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cfai-render")
_CANCEL_FLAGS: dict[str, bool] = {}
_FLAGS_LOCK = threading.Lock()


def _is_cancelled(export_id: str) -> bool:
    with _FLAGS_LOCK:
        return _CANCEL_FLAGS.get(export_id, False)


def request_cancel(export_id: str) -> bool:
    with _FLAGS_LOCK:
        _CANCEL_FLAGS[export_id] = True
    return True


def _update_export(export_id: str, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [export_id]
    with get_db() as db:
        db.execute(f"UPDATE exports SET {assignments} WHERE id = ?", values)


def _make_thumbnail(project_id: str, video_path: Path, duration: float, force: bool) -> None:
    try:
        thumb_dir = PROJECT_MEDIA_DIR / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"{project_id}.jpg"
        if not force and thumb_path.exists():
            return
        at = min(max(0.1, duration * 0.2), max(0.1, duration - 0.1))
        if extract_thumbnail(video_path, thumb_path, at=at, width=640):
            with get_db() as db:
                db.execute(
                    "UPDATE projects SET thumbnail_path = ?, updated_at = ? WHERE id = ?",
                    (relative_to_media(thumb_path), utc_now(), project_id),
                )
    except Exception:
        # A thumbnail failure must not invalidate a successfully rendered video.
        pass


def _run_render(export_id: str) -> None:
    try:
        with get_db() as db:
            export = db.execute("SELECT * FROM exports WHERE id = ?", (export_id,)).fetchone()
            if not export:
                return
            project = db.execute(
                "SELECT * FROM projects WHERE id = ?", (export["project_id"],)
            ).fetchone()
        if not project:
            _update_export(
                export_id,
                status="failed",
                error="Project no longer exists",
                completed_at=utc_now(),
            )
            return
        settings = json.loads(export["settings"] or "{}")
        mode = settings.get("mode", "export")
        data = VideoData.model_validate(json.loads(project["data"] or "{}"))
        _update_export(export_id, status="running", progress=1, error=None)
        last_update = {"time": 0.0, "progress": 0.0}

        def report(value: float) -> None:
            now = time.monotonic()
            if now - last_update["time"] < 1.5 and value < 99:
                return
            last_update["time"] = now
            last_update["progress"] = value
            try:
                _update_export(export_id, progress=round(value, 1))
            except Exception:
                pass

        if mode == "preview":
            output = PREVIEW_DIR / project["id"] / f"preview-{int(time.time())}-{uuid4().hex[:6]}.mp4"
            render_kwargs = {
                "mode": "preview",
                "max_width": int(settings.get("max_width", 640)),
                "crf": 31,
            }
        else:
            output = EXPORT_DIR / project["id"] / f"{project['name'][:40].replace(' ', '-')}-{int(time.time())}.mp4"
            render_kwargs = {
                "mode": "export",
                "width": settings.get("width"),
                "height": settings.get("height"),
                "fps": settings.get("fps"),
                "crf": int(settings.get("crf", 23)),
            }

        probe = render_video(
            dict(project),
            data,
            output,
            progress=report,
            cancel_check=lambda: _is_cancelled(export_id),
            **render_kwargs,
        )
        _make_thumbnail(
            project["id"],
            output,
            probe.get("duration", 0),
            force=(mode == "export"),
        )
        _update_export(
            export_id,
            status="completed",
            progress=100,
            output_path=relative_to_media(output),
            probe=json.dumps(probe),
            error=None,
            completed_at=utc_now(),
        )
    except RenderCancelled:
        _update_export(
            export_id,
            status="cancelled",
            error="Render cancelled",
            completed_at=utc_now(),
        )
    except Exception as exc:
        message = str(exc) or "Render failed"
        if len(message) > 4000:
            message = message[-4000:]
        _update_export(
            export_id,
            status="failed",
            error=message,
            completed_at=utc_now(),
        )
    finally:
        with _FLAGS_LOCK:
            _CANCEL_FLAGS.pop(export_id, None)


def submit_render(export_id: str) -> None:
    with _FLAGS_LOCK:
        _CANCEL_FLAGS[export_id] = False
    _EXECUTOR.submit(_run_render, export_id)


def recover_interrupted_jobs() -> None:
    """Mark jobs left queued/running by a restart as failed instead of pretending they run."""
    try:
        with get_db() as db:
            db.execute(
                """
                UPDATE exports SET status = 'failed', error = ?,
                    completed_at = ?
                WHERE type IN ('video','preview') AND status IN ('queued','running')
                """,
                (
                    "Interrupted by an application restart. Submit the render again.",
                    utc_now(),
                ),
            )
    except Exception:
        pass


def get_export(export_id: str) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM exports WHERE id = ?", (export_id,)).fetchone()
    return dict(row) if row else None
