from __future__ import annotations

import logging
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_NAME, APP_VERSION, FRONTEND_ORIGINS, REPO_ROOT, ensure_directories
from .db import init_db
from .routers import brands, campaigns, chat, copy, design, exports, media, projects, settings, subtitles, system, video, voice
from .services.media import MediaValidationError
from .services.providers import ProviderError
from .services.render_jobs import recover_interrupted_jobs

logger = logging.getLogger("creativeforge")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directories()
    init_db()
    recover_interrupted_jobs()
    logger.info("CreativeForge AI API ready")
    yield
    logger.info("CreativeForge AI API stopped")


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Local-first advertising and creative production API. FREE_ONLY.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-File-Name"],
)


def _error_response(status_code: int, detail: Any, code: str | None = None) -> JSONResponse:
    message = detail if isinstance(detail, str) else "Request failed"
    if not isinstance(detail, str):
        message = str(detail)
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "error": {"code": code or f"http_{status_code}", "message": message},
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, list):
        detail = "; ".join(str(item) for item in detail)
    return _error_response(exc.status_code, detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = f"{location}: {first.get('msg', 'Invalid value')}" if location else first.get("msg", "Invalid request")
    else:
        message = "Invalid request"
    # Pydantic places exception objects in ctx for custom validators. They are not JSON
    # serializable, so expose only the stable, user-facing fields of each error.
    clean_errors = [
        {
            "loc": [str(part) for part in error.get("loc", [])],
            "msg": str(error.get("msg", "Invalid value")),
            "type": str(error.get("type", "value_error")),
        }
        for error in errors
    ]
    return JSONResponse(
        status_code=422,
        content={
            "detail": clean_errors,
            "error": {"code": "validation_error", "message": message},
        },
    )


@app.exception_handler(MediaValidationError)
async def media_error_handler(request: Request, exc: MediaValidationError) -> JSONResponse:
    return _error_response(exc.status_code, str(exc))


@app.exception_handler(ProviderError)
async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
    return _error_response(exc.status_code, str(exc), code=f"provider_error_{exc.provider}")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    logger.debug(traceback.format_exc())
    return _error_response(500, "An unexpected local server error occurred. Check the backend logs.")


for module in (system, settings, chat, brands, campaigns, copy, projects, media, design, video, voice, subtitles, exports):
    app.include_router(module.router)


@app.get("/api")
def api_index() -> dict:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "free_only": True,
        "docs": "/docs",
        "health": "/api/health",
    }


DIST_DIR = REPO_ROOT / "frontend" / "dist"
if DIST_DIR.exists():
    assets = DIST_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        candidate = DIST_DIR / full_path
        try:
            resolved = candidate.resolve()
            if DIST_DIR.resolve() in resolved.parents and resolved.is_file():
                return FileResponse(resolved)
        except (OSError, ValueError):
            pass
        return FileResponse(DIST_DIR / "index.html")
else:

    @app.get("/")
    def root() -> dict:
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "message": "Backend is running. Start the frontend with: cd frontend && npm run dev",
            "docs": "/docs",
        }
