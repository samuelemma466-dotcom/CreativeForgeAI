from __future__ import annotations

import tempfile
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ..config import MAX_UPLOAD_BYTES
from ..services.media import (
    MediaValidationError,
    delete_media,
    get_media,
    list_media,
    media_file,
    store_upload,
)
from ..services.serializers import media_out

router = APIRouter(prefix="/api/media", tags=["media"])


class RawUpload:
    def __init__(self, file: Any, filename: str, content_type: str) -> None:
        self.file = file
        self.filename = filename
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)


@router.get("")
def get_media_list(kind: str | None = None) -> dict:
    if kind and kind not in {"image", "audio", "video"}:
        raise HTTPException(status_code=422, detail="Invalid media kind")
    return {"media": [media_out(row) for row in list_media(kind)]}


@router.post("/upload", status_code=201)
async def upload_multipart(file: UploadFile = File(...)) -> dict:
    try:
        media = await store_upload(file)
    except MediaValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return media_out(media)


@router.put("", status_code=201)
async def upload_raw(
    request: Request,
    x_file_name: str = Header(default="upload", alias="X-File-Name"),
    content_type: str = Header(default="application/octet-stream"),
) -> dict:
    filename = unquote(x_file_name) or "upload"
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Upload exceeds the maximum allowed size")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header")
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Upload exceeds the maximum allowed size")
            spool.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        spool.seek(0)
        media = await store_upload(RawUpload(spool, filename, content_type))
        return media_out(media)
    except MediaValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        spool.close()


@router.get("/{media_id}")
def read_media(media_id: str) -> dict:
    media = get_media(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return media_out(media)


@router.get("/{media_id}/content")
@router.get("/{media_id}/file")
def serve_media(media_id: str) -> FileResponse:
    media = get_media(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media asset not found")
    try:
        path = media_file(media)
    except MediaValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return FileResponse(path, media_type=media["mime_type"])


@router.delete("/{media_id}")
def remove_media(media_id: str) -> dict:
    if not get_media(media_id):
        raise HTTPException(status_code=404, detail="Media asset not found")
    return {"deleted": delete_media(media_id)}
