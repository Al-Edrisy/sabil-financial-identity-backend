"""
app/schemas/kyc.py — KYC request/response schemas.

The service layer returns plain dicts (with PII already decrypted).
`from_attributes=True` is kept so FastAPI can also serialize ORM objects.
"""

from pydantic import BaseModel, computed_field
from typing import Optional, Any, List, Dict
from datetime import datetime, timezone
from enum import Enum
from app.models.kyc import KYCStatus


class IDType(str, Enum):
    national_id      = "national_id"
    passport         = "passport"
    drivers_license  = "drivers_license"
    residence_permit = "residence_permit"


# ---------------------------------------------------------------------------
# Base schemas
# ---------------------------------------------------------------------------
class KYCBase(BaseModel):
    id_type:   Optional[str] = None
    id_number: Optional[str] = None


class KYCUpdate(KYCBase):
    status:           Optional[KYCStatus] = None
    ocr_data:         Optional[Any]       = None
    face_match_score: Optional[float]     = None


# ---------------------------------------------------------------------------
# Liveness details sub-schema
# ---------------------------------------------------------------------------
class LivenessDetails(BaseModel):
    sharpness_score:  Optional[float] = None
    frequency_score:  Optional[float] = None
    reason:           Optional[str]   = None


# ---------------------------------------------------------------------------
# DB-backed response schema
# ---------------------------------------------------------------------------
class KYCInDBBase(KYCBase):
    id:                  int
    user_id:             int
    status:              KYCStatus

    # Document identity (decrypted by service layer)
    nationality:         Optional[str]      = None
    country:             Optional[str]      = None
    full_name:           Optional[str]      = None
    dob:                 Optional[datetime] = None
    gender:              Optional[str]      = None

    # Document validity
    document_expires_at: Optional[datetime] = None
    document_issued_at:  Optional[datetime] = None

    # AI scores
    face_match_score:    Optional[float]    = None
    liveness_score:      Optional[float]    = None
    liveness_details:    Optional[LivenessDetails] = None
    authenticity_score:  Optional[float]    = None

    # Outcome
    rejection_reason:    Optional[str]      = None

    # Lifecycle
    attempt_count:       int                = 0
    id_image_url:        Optional[str]      = None
    selfie_image_url:    Optional[str]      = None
    expires_at:          Optional[datetime] = None

    # Admin review
    reviewer_note:       Optional[str]      = None
    reviewed_at:         Optional[datetime] = None

    # Timestamps
    created_at:          datetime
    updated_at:          Optional[datetime] = None

    # ocr_data is admin-only — excluded from end-user response
    # (included in KYCAdminResponse below)

    model_config = {"from_attributes": True}


class KYCResponse(KYCInDBBase):
    """End-user response — no raw OCR data."""

    @computed_field
    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at < datetime.now(timezone.utc)

    @computed_field
    @property
    def verification_summary(self) -> str:
        """Human-readable one-line summary of the verification result."""
        status_map = {
            KYCStatus.VERIFIED:    "Identity verified successfully.",
            KYCStatus.PENDING:     "Under manual review — we'll notify you shortly.",
            KYCStatus.REJECTED:    f"Verification failed. {self.rejection_reason or 'Please resubmit with clearer images.'}",
            KYCStatus.RESUBMITTED: "Resubmission received and processing.",
        }
        return status_map.get(self.status, "Unknown status.")


class KYCAdminResponse(KYCInDBBase):
    """Admin response — includes raw OCR data."""
    ocr_data: Optional[Any] = None

    @computed_field
    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at < datetime.now(timezone.utc)


class KYCListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     List[KYCAdminResponse]   # admin list uses full response


class KYCAdminReviewRequest(BaseModel):
    approved: bool
    note:     Optional[str] = "Manual admin review"
