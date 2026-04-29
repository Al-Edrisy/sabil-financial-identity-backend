"""
app/api/v1/routes/auth.py — Authentication endpoints.

Step 1 of the user flow:
  POST /auth/send-otp    — send OTP to phone number
  POST /auth/verify-otp  — verify OTP, create/return user + access token
  POST /auth/login       — Firebase token login (backward compat)
"""

from fastapi import APIRouter, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.dependencies.db import get_db
from app.dependencies.rate_limit import rate_limiter
from app.dependencies.auth import create_access_token
from app.services.auth_service import AuthService
from app.schemas.user import (
    User as UserSchema,
    SendOTPRequest,
    VerifyOTPRequest,
    OTPResponse,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schema for verify-otp (user + token)
# ---------------------------------------------------------------------------
class AuthResponse(BaseModel):
    """Returned after successful OTP verification."""
    access_token: str
    token_type:   str = "bearer"
    user:         UserSchema

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# POST /auth/send-otp
# ---------------------------------------------------------------------------
@router.post(
    "/send-otp",
    response_model=OTPResponse,
    summary="Step 1a — Send OTP to Phone Number",
    description=(
        "Sends a one-time password to the provided phone number. "
        "**Dev bypass:** phone `+96742424242` always receives code `7744`. "
        "Rate limited to 3 requests per minute per IP."
    ),
    dependencies=[Depends(rate_limiter(requests_per_minute=3))],
)
async def send_otp(
    request: SendOTPRequest,
    db:      AsyncSession = Depends(get_db),
) -> OTPResponse:
    service = AuthService(db)
    result  = await service.send_otp(
        phone_number = request.phone_number,
        country_code = request.country_code,
    )
    return OTPResponse(**result)


# ---------------------------------------------------------------------------
# POST /auth/verify-otp
# ---------------------------------------------------------------------------
@router.post(
    "/verify-otp",
    response_model=AuthResponse,
    summary="Step 1b — Verify OTP and Create/Login User",
    description=(
        "Verifies the OTP code. On success, creates a new account (first time) "
        "or logs in the existing user. "
        "Returns `access_token` (use as `Authorization: Bearer <token>`) and the user profile. "
        "**Dev bypass:** phone `+96742424242` with code `7744` always succeeds."
    ),
    dependencies=[Depends(rate_limiter(requests_per_minute=5))],
)
async def verify_otp(
    request: VerifyOTPRequest,
    db:      AsyncSession = Depends(get_db),
) -> AuthResponse:
    service = AuthService(db)
    user    = await service.verify_otp(
        phone_number = request.phone_number,
        otp_code     = request.otp_code,
        full_name    = request.full_name,
        country_code = request.country_code,
    )
    token = create_access_token(
        user_id      = user.id,
        phone_number = user.phone_number or "",
    )
    return AuthResponse(access_token=token, user=user)


# ---------------------------------------------------------------------------
# POST /auth/login  (Firebase token — backward compat)
# ---------------------------------------------------------------------------
@router.post(
    "/login",
    response_model=UserSchema,
    summary="Authenticate via Firebase Token",
    description=(
        "Verifies a Firebase ID token and returns the user profile. "
        "Creates a new user account and wallet on first login. "
        "Use `/auth/send-otp` + `/auth/verify-otp` for the phone OTP flow."
    ),
    dependencies=[Depends(rate_limiter(requests_per_minute=5))],
)
async def login(
    id_token: str = Body(..., embed=True, description="Firebase ID token from client SDK"),
    db: AsyncSession = Depends(get_db),
) -> UserSchema:
    service = AuthService(db)
    return await service.authenticate_user(id_token)
