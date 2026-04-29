from sqlalchemy import Column, Integer, String, Float, Enum, ForeignKey, DateTime, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.database.session import Base

class KYCStatus(enum.Enum):
    PENDING      = "pending"
    VERIFIED     = "verified"
    REJECTED     = "rejected"
    RESUBMITTED  = "resubmitted"  # in-flight re-attempt after a rejection

class KYC(Base):
    __tablename__ = "kyc_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    status = Column(Enum(KYCStatus), default=KYCStatus.PENDING)
    is_active = Column(Boolean, default=True, nullable=False)
    id_type = Column(String)
    id_number = Column(String)
    id_number_hash = Column(String, index=True) # Deterministic hash for lookups
    nationality = Column(String)
    country = Column(String)
    full_name = Column(String)
    dob = Column(String)
    gender = Column(String)
    document_expires_at = Column(DateTime(timezone=True))
    ocr_data = Column(String)         # Encrypted OCR JSON blob
    face_match_score = Column(Float)  # 0–1 confidence from DeepFace
    liveness_score = Column(Float)    # Laplacian variance of selfie
    authenticity_score = Column(Float) # Heuristic doc-check composite (0–1)
    attempt_count = Column(Integer, default=0, nullable=False)  # resubmission counter
    id_image_url = Column(String)
    selfie_image_url = Column(String)
    # Expiry: set to now() + KYC_EXPIRY_DAYS when status becomes VERIFIED
    expires_at = Column(DateTime(timezone=True), nullable=True)
    # Manual review audit trail
    reviewer_id   = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_note = Column(String, nullable=True)
    reviewed_at   = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # server_default ensures updated_at is populated on INSERT as well as UPDATE
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="kyc_records", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
