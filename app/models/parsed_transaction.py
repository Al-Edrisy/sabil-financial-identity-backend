"""
app/models/parsed_transaction.py — Stores individual transaction rows
extracted from uploaded bank statements / receipts via the OCR pipeline.

Each row belongs to an upload_id (a single statement upload) and a user.
The categorizer and signal service read from this table.
"""

import enum
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    ForeignKey, DateTime, Date, Enum, Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.session import Base


class ParsedTransactionType(enum.Enum):
    INCOME  = "income"
    EXPENSE = "expense"
    UNKNOWN = "unknown"


class ParsedTransactionSource(enum.Enum):
    OCR_UPLOAD = "ocr_upload"   # extracted from an uploaded image
    MANUAL     = "manual"       # entered or corrected by the user


class ParsedTransaction(Base):
    __tablename__ = "parsed_transactions"

    id                = Column(Integer, primary_key=True, index=True)

    # ── Ownership ─────────────────────────────────────────────────────────────
    user_id           = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    upload_id         = Column(String, nullable=False, index=True)   # groups rows from the same upload

    # ── Raw OCR data ──────────────────────────────────────────────────────────
    raw_line          = Column(String, nullable=True)                # original OCR line before parsing

    # ── Parsed fields ─────────────────────────────────────────────────────────
    description       = Column(String, nullable=False)
    amount            = Column(Float, nullable=False)
    currency          = Column(String, nullable=False, default="USD")
    normalized_amount = Column(Float, nullable=True)                 # always in USD via fx.py
    type              = Column(
        Enum(ParsedTransactionType),
        nullable=False,
        default=ParsedTransactionType.UNKNOWN,
    )
    category          = Column(String, nullable=True)                # set by categorizer_service
    transaction_date  = Column(Date, nullable=True)                  # parsed date from statement

    # ── Quality signals ───────────────────────────────────────────────────────
    confidence        = Column(Float, nullable=False, default=0.0)   # parser confidence 0.0–1.0
    needs_review      = Column(Boolean, nullable=False, default=False)  # flagged for human review

    # ── Source tracking ───────────────────────────────────────────────────────
    source            = Column(
        Enum(ParsedTransactionSource),
        nullable=False,
        default=ParsedTransactionSource.OCR_UPLOAD,
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at        = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ── Relationships ─────────────────────────────────────────────────────────
    user = relationship("User", back_populates="parsed_transactions")

    # ── Composite indexes for common query patterns ───────────────────────────
    __table_args__ = (
        Index("ix_parsed_tx_user_upload", "user_id", "upload_id"),
        Index("ix_parsed_tx_user_type",   "user_id", "type"),
        Index("ix_parsed_tx_needs_review","user_id", "needs_review"),
    )

    def __repr__(self) -> str:
        return (
            f"<ParsedTransaction id={self.id} user={self.user_id} "
            f"desc='{self.description[:30]}' amount={self.amount} {self.currency} "
            f"type={self.type.value if self.type else 'unknown'}>"
        )
