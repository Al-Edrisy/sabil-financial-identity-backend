"""
app/dependencies/auth.py — Authentication dependency.

Supports two token types:
  1. Firebase ID token  — for Firebase-authenticated users (existing flow)
  2. Sabil JWT          — issued by /auth/verify-otp for phone-OTP users

Both resolve to a User model instance.
"""

import json
import base64
import hmac
import hashlib
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.firebase import verify_firebase_token
from app.dependencies.db import get_db
from app.models.user import User as UserModel
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)
security = HTTPBearer()


# ---------------------------------------------------------------------------
# Minimal JWT implementation (no external library needed for MVP)
# ---------------------------------------------------------------------------
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def create_access_token(user_id: int, phone_number: str) -> str:
    """Create a signed JWT for a phone-OTP authenticated user."""
    header  = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub":   str(user_id),
        "phone": phone_number,
        "iat":   int(time.time()),
        "exp":   int(time.time()) + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "type":  "sabil_otp",
    }).encode())
    signing_input = f"{header}.{payload}"
    sig = hmac.new(
        settings.SECRET_KEY.encode(),
        signing_input.encode(),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64url_encode(sig)}"


def _verify_sabil_jwt(token: str) -> Optional[dict]:
    """Verify a Sabil-issued JWT. Returns payload dict or None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig  = hmac.new(
            settings.SECRET_KEY.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("type") != "sabil_otp":
            return None
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main dependency
# ---------------------------------------------------------------------------
async def get_current_user(
    res: HTTPAuthorizationCredentials = Depends(security),
    db:  AsyncSession                 = Depends(get_db),
) -> UserModel:
    """
    Resolve the current user from either:
      - A Firebase ID token (existing flow)
      - A Sabil JWT issued by /auth/verify-otp (OTP flow)
    """
    token = res.credentials

    # ── Try Sabil JWT first (faster, no network call) ─────────────────────────
    sabil_payload = _verify_sabil_jwt(token)
    if sabil_payload:
        user_id = int(sabil_payload["sub"])
        result  = await db.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated.",
            )
        return user

    # ── Try Firebase token ────────────────────────────────────────────────────
    decoded_token = verify_firebase_token(token)
    if not decoded_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    firebase_uid = decoded_token.get("uid")
    phone_number = decoded_token.get("phone_number")

    # Try by firebase_uid first
    result = await db.execute(
        select(UserModel).where(UserModel.firebase_uid == firebase_uid)
    )
    user = result.scalar_one_or_none()

    # Fall back to phone number (OTP user who later linked Firebase)
    if user is None and phone_number:
        result = await db.execute(
            select(UserModel).where(UserModel.phone_number == phone_number)
        )
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please complete registration via /auth/send-otp.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    return user
