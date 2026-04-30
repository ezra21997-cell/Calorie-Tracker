"""
FastAPI application entry-point.

Creates the ``app`` instance, registers middleware, mounts routes,
and handles the application lifespan (DB init on startup).

Run locally::

    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.dashboard import dashboard_router
from api.routes import router
from config.settings import get_settings
from storage.db import init_db
from utils.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(level=settings.log_level, use_json=settings.log_json)
logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """
    Manage application startup and shutdown.

    Startup:  initialise database tables.
    Shutdown: (place connection pool teardown here if needed).
    """
    logger.info("Starting trend-scraper API…")
    init_db()
    yield
    logger.info("Shutting down trend-scraper API.")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    Construct and return the configured FastAPI application.

    Separating construction from the module-level ``app`` variable makes
    unit-testing easier (you can call ``create_app()`` with test overrides).
    """
    application = FastAPI(
        title="Trend Scraper API",
        description=(
            "Detects and exposes viral trends ingested from multiple internet "
            "sources (Reddit, Google Trends, …).  "
            "Scores are computed using a velocity-based algorithm with "
            "configurable time-decay."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global exception handler ──────────────────────────────────────────
    @application.exception_handler(Exception)
    async def _unhandled_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )

    # ── Routes ────────────────────────────────────────────────────────────
    application.include_router(router, prefix="")
    application.include_router(dashboard_router, prefix="")

    return application


app: FastAPI = create_app()


# ── Direct execution (python -m api.main) ─────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        log_level=settings.log_level.lower(),
    )
