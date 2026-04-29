"""
app/schemas/user.py — User request/response schemas.
"""

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime
import re


# ---------------------------------------------------------------------------
# Phone number validator
# ---------------------------------------------------------------------------
def _validate_phone(v: Optional[str]) -> Optional[str]:
    """Normalize phone to E.164 format. Accepts +XXXXXXXXXXX or digits only."""
    if v is None or v == "pending":
        return v
    digits = re.sub(r"[^\d+]", "", v)
    if not digits.startswith("+"):
        digits = "+" + digits
    if len(digits) < 8 or len(digits) > 16:
        raise ValueError("Phone number must be 7–15 digits (E.164 format)")
    return digits


# ---------------------------------------------------------------------------
# OTP schemas
# ---------------------------------------------------------------------------
class SendOTPRequest(BaseModel):
    phone_number: str
    country_code: Optional[str] = None   # ISO country code e.g. "YE", "SA"

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        result = _validate_phone(v)
        if result is None:
            raise ValueError("Phone number is required")
        return result


class VerifyOTPRequest(BaseModel):
    phone_number: str
    otp_code:     str
    full_name:    Optional[str] = None   # optional on first registration
    country_code: Optional[str] = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        result = _validate_phone(v)
        if result is None:
            raise ValueError("Phone number is required")
        return result

    @field_validator("otp_code")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) not in (4, 6):
            raise ValueError("OTP must be 4 or 6 digits")
        return v


class OTPResponse(BaseModel):
    message:      str
    phone_number: str
    expires_in:   int = 300   # seconds


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------
class UserBase(BaseModel):
    phone_number: Optional[str] = None
    full_name:    Optional[str] = None
    country_code: Optional[str] = None


class UserCreate(UserBase):
    firebase_uid: Optional[str] = None
    email:        Optional[str] = None
    phone_number: str


class UserUpdate(BaseModel):
    """All fields optional — only provided fields are updated."""
    email:        Optional[EmailStr] = None
    phone_number: Optional[str]      = None
    full_name:    Optional[str]      = None
    country_code: Optional[str]      = None
    is_active:    Optional[bool]     = None


class OnboardingStatus(BaseModel):
    """Returned by GET /users/me/onboarding-status"""
    onboarding_step:  int
    phone_verified:   bool
    kyc_status:       Optional[str]   = None   # pending|verified|rejected|not_started
    credit_status:    Optional[str]   = None   # scored|not_started
    next_step:        str
    next_step_url:    str


class UserInDBBase(UserBase):
    id:               int
    firebase_uid:     Optional[str]   = None
    email:            Optional[str]   = None
    is_active:        bool
    is_admin:         bool
    phone_verified:   bool            = False
    onboarding_step:  int             = 0
    wallet_balance:   Optional[float] = None
    kyc_status:       Optional[str]   = None
    credit_score:     Optional[int]   = None
    created_at:       datetime
    updated_at:       Optional[datetime] = None

    model_config = {"from_attributes": True}


class User(UserInDBBase):
    pass
