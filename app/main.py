"""
Sabil Financial Identity Backend
FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logger import get_logger
from app.exceptions.handlers import register_exception_handlers
from app.middleware.logging_middleware import LoggingMiddleware

logger = get_logger(__name__)


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Sabil — Financial Identity Backend API",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware ──────────────────────────────────────────────────────
    application.add_middleware(LoggingMiddleware)

    # ── Routers ───────────────────────────────────────────────────────────────
    application.include_router(api_router, prefix=settings.API_V1_STR)

    # ── Exception handlers ────────────────────────────────────────────────────
    register_exception_handlers(application)

    return application


app = create_application()


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("🚀 Sabil backend starting up…")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("🛑 Sabil backend shutting down…")
