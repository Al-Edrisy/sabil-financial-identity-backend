"""
Sabil Financial Identity Backend
FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.v1.websockets import notifications
from app.core.config import settings
from app.core.logger import get_logger
from app.database import base  # noqa: F401 - Register models
from app.exceptions.handlers import register_exception_handlers
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.security_headers_middleware import SecurityHeadersMiddleware

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
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware ──────────────────────────────────────────────────────
    application.add_middleware(LoggingMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)

    # ── Routers ───────────────────────────────────────────────────────────────
    application.include_router(api_router, prefix=settings.API_V1_STR)
    application.include_router(notifications.router)

    # ── Exception handlers ────────────────────────────────────────────────────
    register_exception_handlers(application)

    return application


app = create_application()


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("🚀 Sabil backend starting up…")
    
    # ── Database Schema Sync ─────────────────────────────────────────────────
    from app.database.session import engine
    from app.database.base import Base
    from sqlalchemy import text
    try:
        async with engine.begin() as conn:
            logger.info("🔧 Synchronizing database schema…")
            await conn.run_sync(Base.metadata.create_all)
            
            # Manual column additions for existing tables (metadata.create_all doesn't ALTER)
            logger.info("🛠️ Checking for missing columns in kyc_records…")
            await conn.execute(text("ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS full_name VARCHAR;"))
            await conn.execute(text("ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS dob VARCHAR;"))
            await conn.execute(text("ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS gender VARCHAR;"))
            
            logger.info("✅ Schema synchronization complete.")
    except Exception as e:
        logger.error(f"❌ Schema sync failed: {e}")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("🛑 Sabil backend shutting down…")
