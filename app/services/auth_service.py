"""
app/services/auth_service.py — Authentication service.

Handles:
  - Phone OTP send/verify (dev bypass for MVP)
  - Firebase token login (existing flow)
  - User creation on first login
"""

import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.core.firebase import verify_firebase_token
from app.services.user_service import UserService
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.user import UserCreate
from app.core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Dev OTP store — in-memory for MVP
# In production: replace with Redis (TTL-based) or a DB table
# ---------------------------------------------------------------------------
# Structure: { phone_number: {"code": "7744", "expires_at": datetime} }
_OTP_STORE: dict[str, dict] = {}

# ── Dev bypass configuration ──────────────────────────────────────────────────
# Any phone matching DEV_PHONE always gets DEV_OTP_CODE without sending SMS
DEV_PHONE    = "+96742424242"    # +967 4242424242 normalized
DEV_OTP_CODE = "7744"
OTP_TTL_SECONDS = 300            # 5 minutes


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db           = db
        self.user_service = UserService(db)

    # ── OTP flow ──────────────────────────────────────────────────────────────

    async def send_otp(self, phone_number: str, country_code: Optional[str] = None) -> dict:
        """
        Generate and 'send' an OTP to the given phone number.

        Dev bypass: +96742424242 always gets code 7744 without SMS.
        All other numbers: generate a random 6-digit code (log it for dev).
        Production: integrate Twilio / Firebase SMS here.
        """
        # Normalize phone
        phone = phone_number.strip()

        # Dev bypass
        dev_phones = {DEV_PHONE, "+96755555555", "+967111111111", "+967222222222"}
        if phone in dev_phones:
            code = DEV_OTP_CODE
            logger.info(f"[DEV] OTP for {phone}: {code} (dev bypass)")
        else:
            # Generate random 6-digit code
            code = "".join(random.choices(string.digits, k=6))
            logger.info(f"[DEV] OTP for {phone}: {code} (would send SMS in production)")
            # TODO production: await sms_client.send(phone, f"Your Sabil code: {code}")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)
        _OTP_STORE[phone] = {"code": code, "expires_at": expires_at, "attempts": 0}

        return {
            "message":      "OTP sent successfully.",
            "phone_number": phone,
            "expires_in":   OTP_TTL_SECONDS,
        }

    async def verify_otp(
        self,
        phone_number: str,
        otp_code:     str,
        full_name:    Optional[str] = None,
        country_code: Optional[str] = None,
    ) -> User:
        """
        Verify OTP and return (or create) the user.

        On success:
          - Marks phone as verified
          - Creates user if first time
          - Advances onboarding_step to 1
          - Creates wallet if missing
        """
        phone = phone_number.strip()
        code  = otp_code.strip()

        # ── Validate OTP ──────────────────────────────────────────────────────
        stored = _OTP_STORE.get(phone)

        if stored is None:
            logger.warning(f"Verify OTP failed for {phone}: No OTP found in store.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No OTP found for this phone number. Please request a new code.",
            )

        # Check expiry
        if datetime.now(timezone.utc) > stored["expires_at"]:
            _OTP_STORE.pop(phone, None)
            logger.warning(f"Verify OTP failed for {phone}: OTP expired.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP has expired. Please request a new code.",
            )

        # Rate-limit attempts (max 5 per OTP)
        stored["attempts"] += 1
        if stored["attempts"] > 5:
            _OTP_STORE.pop(phone, None)
            logger.warning(f"Verify OTP failed for {phone}: Too many attempts.")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many incorrect attempts. Please request a new OTP.",
            )

        # Check code
        if stored["code"] != code:
            logger.warning(f"Verify OTP failed for {phone}: Incorrect code (expected {stored['code']}, got {code}).")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incorrect OTP code. {5 - stored['attempts'] + 1} attempt(s) remaining.",
            )

        # ── OTP valid — clear it ──────────────────────────────────────────────
        _OTP_STORE.pop(phone, None)

        # ── Find or create user ───────────────────────────────────────────────
        result = await self.db.execute(
            select(User).where(User.phone_number == phone)
        )
        user = result.scalar_one_or_none()

        if user is None:
            # First time — create account
            user = User(
                phone_number    = phone,
                country_code    = country_code,
                full_name       = full_name,
                phone_verified  = True,
                onboarding_step = 1,
                is_active       = True,
            )
            self.db.add(user)
            await self.db.flush()
            await self.db.refresh(user)

            # Create wallet
            wallet = Wallet(user_id=user.id, balance=0.0, currency="USD")
            self.db.add(wallet)
            await self.db.commit()
            await self.db.refresh(user)
            logger.info(f"New user created via OTP: id={user.id} phone={phone}")
        else:
            # Returning user — mark phone verified, advance step if needed
            user.phone_verified = True
            if user.onboarding_step < 1:
                user.onboarding_step = 1
            if country_code and not user.country_code:
                user.country_code = country_code
            if full_name and not user.full_name:
                user.full_name = full_name
            await self.db.commit()
            await self.db.refresh(user)
            logger.info(f"Returning user verified via OTP: id={user.id} phone={phone}")

        return await self.user_service.get_user(user.id)

    # ── Firebase token login (existing flow, kept for backward compat) ────────

    async def authenticate_user(self, id_token: str) -> User:
        """
        Verify Firebase ID token and return or create user.
        Used when client handles Firebase auth (e.g. Google Sign-In).
        """
        decoded_token = verify_firebase_token(id_token)
        if not decoded_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Firebase token.",
            )

        firebase_uid = decoded_token.get("uid")
        email        = decoded_token.get("email")
        full_name    = decoded_token.get("name", "")
        phone_number = decoded_token.get("phone_number")   # may be None

        # Try to find by firebase_uid first
        result = await self.db.execute(
            select(User).where(User.firebase_uid == firebase_uid)
        )
        user = result.scalar_one_or_none()

        # If not found by firebase_uid, try by phone (OTP user linking)
        if user is None and phone_number:
            result = await self.db.execute(
                select(User).where(User.phone_number == phone_number)
            )
            user = result.scalar_one_or_none()
            if user:
                # Link Firebase UID to existing phone user
                user.firebase_uid = firebase_uid
                if email and not user.email:
                    user.email = email

        if user is None:
            # Brand new user via Firebase
            user = User(
                firebase_uid    = firebase_uid,
                email           = email,
                phone_number    = phone_number,
                full_name       = full_name or "",
                phone_verified  = bool(phone_number),
                onboarding_step = 1 if phone_number else 0,
                is_active       = True,
            )
            self.db.add(user)
            await self.db.flush()
            await self.db.refresh(user)

            wallet = Wallet(user_id=user.id, balance=0.0, currency="USD")
            self.db.add(wallet)

        await self.db.commit()
        await self.db.refresh(user)
        return await self.user_service.get_user(user.id)
