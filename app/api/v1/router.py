from fastapi import APIRouter
from app.api.v1.routes import auth, kyc, health, user, wallet, admin_kyc, credit, admin_credit

api_router = APIRouter()

# ── Core ──────────────────────────────────────────────────────────────────────
api_router.include_router(health.router,        prefix="/health",        tags=["health"])
api_router.include_router(auth.router,          prefix="/auth",          tags=["auth"])
api_router.include_router(user.router,          prefix="/users",         tags=["users"])
api_router.include_router(wallet.router,        prefix="/wallet",        tags=["wallet"])

# ── KYC ───────────────────────────────────────────────────────────────────────
api_router.include_router(kyc.router,           prefix="/kyc",           tags=["kyc"])
api_router.include_router(admin_kyc.router,     prefix="/admin/kyc",     tags=["admin — kyc"])

# ── Credit Scoring ────────────────────────────────────────────────────────────
api_router.include_router(credit.router,        prefix="/credit",        tags=["credit scoring"])
api_router.include_router(admin_credit.router,  prefix="/admin/credit",  tags=["admin — credit"])
