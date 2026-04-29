"""
app/schemas/kyc.py — KYC request/response schemas.

The service layer returns plain dicts (with PII already decrypted).
Pydantic v2 handles dict → model validation natively.
`from_attributes=True` is kept so FastAPI can also serialize ORM objects
directly if needed (e.g. in tests), but the primary path is dict input.
"""

from pydantic import BaseModel, computed_field, model_validator
from typing import Optional, Any, List
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
# DB-backed response schema
# ---------------------------------------------------------------------------
class KYCInDBBase(KYCBase):
    id:                  int
    user_id:             int
    status:              KYCStatus
    nationality:         Optional[str]      = None
    country:             Optional[str]      = None
    full_name:           Optional[str]      = None
    dob:                 Optional[datetime] = None
    gender:              Optional[str]      = None
    document_expires_at: Optional[datetime] = None
    ocr_data:            Optional[Any]      = None
    face_match_score:    Optional[float]    = None
    liveness_score:      Optional[float]    = None
    authenticity_score:  Optional[float]    = None
    attempt_count:       int                = 0
    id_image_url:        Optional[str]      = None
    selfie_image_url:    Optional[str]      = None
    expires_at:          Optional[datetime] = None
    reviewer_note:       Optional[str]      = None
    reviewed_at:         Optional[datetime] = None
    created_at:          datetime
    # updated_at is optional — may be None on fresh inserts before DB trigger fires
    updated_at:          Optional[datetime] = None

    model_config = {"from_attributes": True}


class KYCResponse(KYCInDBBase):
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
    items:     List[KYCResponse]


class KYCAdminReviewRequest(BaseModel):
    approved: bool
    note:     Optional[str] = "Manual admin review"
