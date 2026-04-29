"""
app/models/kyc.py — KYC verification record.
"""

from sqlalchemy import Column, Integer, String, Float, Enum, ForeignKey, DateTime, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.database.session import Base


class KYCStatus(enum.Enum):
    PENDING     = "pending"
    VERIFIED    = "verified"
    REJECTED    = "rejected"
    RESUBMITTED = "resubmitted"   # in-flight re-attempt after a rejection


class KYC(Base):
    __tablename__ = "kyc_records"

    id      = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    status  = Column(Enum(KYCStatus), default=KYCStatus.PENDING)
    is_active = Column(Boolean, default=True, nullable=False)

    # ── Document identity fields (PII-encrypted) ──────────────────────────────
    id_type        = Column(String)
    id_number      = Column(String)                          # encrypted
    id_number_hash = Column(String, index=True)              # deterministic hash for lookups
    nationality    = Column(String)                          # encrypted
    country        = Column(String)                          # encrypted
    full_name      = Column(String)                          # encrypted
    dob            = Column(String)                          # encrypted ISO date string
    gender         = Column(String)                          # M / F / X (not encrypted)

    # ── Document validity ─────────────────────────────────────────────────────
    document_issued_at  = Column(DateTime(timezone=True), nullable=True)   # issue date
    document_expires_at = Column(DateTime(timezone=True))

    # ── AI pipeline scores ────────────────────────────────────────────────────
    ocr_data           = Column(String)    # encrypted JSON blob of full OCR output
    face_match_score   = Column(Float)     # 0–1 confidence from DeepFace VGG-Face
    liveness_score     = Column(Float)     # Laplacian variance of selfie
    liveness_details   = Column(JSON)      # {sharpness_score, frequency_score, reason}
    authenticity_score = Column(Float)     # heuristic doc-check composite (0–1)

    # ── Outcome ───────────────────────────────────────────────────────────────
    rejection_reason = Column(String, nullable=True)   # human-readable rejection cause

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    attempt_count    = Column(Integer, default=0, nullable=False)
    id_image_url     = Column(String)
    selfie_image_url = Column(String)
    expires_at       = Column(DateTime(timezone=True), nullable=True)

    # ── Manual review audit trail ─────────────────────────────────────────────
    reviewer_id   = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_note = Column(String, nullable=True)
    reviewed_at   = Column(DateTime(timezone=True), nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ── Relationships ─────────────────────────────────────────────────────────
    user     = relationship("User", back_populates="kyc_records", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
