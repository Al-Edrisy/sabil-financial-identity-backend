from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from app.models.kyc import KYCStatus

class KYCBase(BaseModel):
    id_type: Optional[str] = None
    id_number: Optional[str] = None

class KYCUpdate(KYCBase):
    status: Optional[KYCStatus] = None
    ocr_data: Optional[Any] = None
    face_match_score: Optional[float] = None

class KYCInDBBase(KYCBase):
    id: int
    user_id: int
    status: KYCStatus
    created_at: datetime

    class Config:
        from_attributes = True

class KYCResponse(KYCInDBBase):
    pass
