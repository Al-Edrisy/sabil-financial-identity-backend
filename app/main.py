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

            # Add new columns to existing tables (idempotent — IF NOT EXISTS)
            logger.info("🛠️  Checking for missing columns…")
            migrations = [
                # users table — new onboarding fields
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS country_code VARCHAR(4);",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_step SMALLINT NOT NULL DEFAULT 0;",
                # Make email and phone nullable for phone-only users
                "ALTER TABLE users ALTER COLUMN email DROP NOT NULL;",
                "ALTER TABLE users ALTER COLUMN phone_number DROP NOT NULL;",
                "ALTER TABLE users ALTER COLUMN firebase_uid DROP NOT NULL;",
                # kyc_records — issue date
                "ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS document_issued_at TIMESTAMPTZ;",
                "ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS full_name VARCHAR;",
                "ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS dob VARCHAR;",
                "ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS gender VARCHAR;",
                "ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR;",
                "ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS liveness_details JSONB;",
                "ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS id_number_hash VARCHAR;",
            ]
            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                except Exception as col_err:
                    logger.debug(f"Migration skipped (likely already applied): {col_err}")

            logger.info("✅ Schema synchronization complete.")

    except Exception as e:
        logger.error(f"❌ Schema sync failed: {e}")

    # ── Seed Test Data (independent — never blocks startup) ──────────────────
    try:
        from app.utils.seed_test_data import seed_test_users
        from app.database.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await seed_test_users(session)
    except Exception as seed_err:
        logger.warning(f"⚠️  Test data seeding skipped: {seed_err}")

    # ── Pre-warm AI Models (background — doesn't block startup or --reload) ──
    import asyncio as _asyncio

    async def _prewarm():
        try:
            from app.ai.ocr import get_ocr_reader, get_statement_ocr_reader
            logger.info("🤖 Pre-warming AI models in background...")
            await _asyncio.to_thread(get_ocr_reader)
            await _asyncio.to_thread(get_statement_ocr_reader)
            logger.info("✅ AI models pre-warmed and ready.")
        except Exception as ai_err:
            logger.warning(f"⚠️  AI pre-warming failed or skipped: {ai_err}")

    _asyncio.ensure_future(_prewarm())



@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("🛑 Sabil backend shutting down…")
