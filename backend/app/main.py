"""FastAPI application.

Run from the `backend` directory:

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import PROJECT_ROOT, settings
from app.services.glm_client import GlmConfigurationError
from app.services.parsers import UploadValidationError
from app.services.pdf_parser import PdfError
from app.services.storage import SessionNotFound

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Бенчмарк мультимодальной модели GLM 4.6 в задаче извлечения содержимого "
        "документов: CER, WER, exact success, время ответа и расход токенов."
    ),
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploaded pages, crops and results are served straight from the data directory.
app.mount("/static", StaticFiles(directory=str(settings.data_path)), name="static")

app.include_router(router)


# --------------------------------------------------------------------------- #
#  error handling: user-facing messages instead of stack traces
# --------------------------------------------------------------------------- #


@app.exception_handler(UploadValidationError)
async def _validation_handler(request: Request, exc: UploadValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "code": exc.code},
    )


@app.exception_handler(SessionNotFound)
async def _session_handler(request: Request, exc: SessionNotFound):
    return JSONResponse(
        status_code=404, content={"detail": str(exc), "code": "session_not_found"}
    )


@app.exception_handler(GlmConfigurationError)
async def _glm_config_handler(request: Request, exc: GlmConfigurationError):
    return JSONResponse(
        status_code=400, content={"detail": str(exc), "code": "glm_not_configured"}
    )


@app.exception_handler(PdfError)
async def _pdf_handler(request: Request, exc: PdfError):
    return JSONResponse(
        status_code=422, content={"detail": str(exc), "code": "pdf_error"}
    )


@app.get("/", include_in_schema=False)
def index():
    """Serve the built SPA when `frontend/dist` exists, otherwise explain setup."""
    dist_index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if dist_index.exists():
        return FileResponse(dist_index)
    return {
        "app": settings.app_name,
        "status": "backend only",
        "hint": (
            "Соберите фронтенд (cd frontend && npm install && npm run build) "
            "или запустите Vite dev-сервер: npm run dev (http://localhost:5173)."
        ),
        "api_docs": "/api/docs",
        "health": "/api/health",
    }


def _mount_frontend_dist() -> None:
    """Serve hashed assets of the production build, if present."""
    dist = PROJECT_ROOT / "frontend" / "dist"
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="spa-assets")


_mount_frontend_dist()


def _frontend_dir_exists() -> bool:
    return (PROJECT_ROOT / "frontend" / "dist" / "index.html").exists()


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """SPA history fallback (only when a production build is present)."""
    dist = Path(PROJECT_ROOT) / "frontend" / "dist"
    candidate = dist / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    if _frontend_dir_exists():
        return FileResponse(dist / "index.html")
    return JSONResponse(status_code=404, content={"detail": "Not Found"})
