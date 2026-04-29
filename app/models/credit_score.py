"""
app/models/credit_score.py — Stores the computed credit score and signals
for each user. One active record per user; previous scores are soft-archived
via is_active=False so history is preserved.
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    ForeignKey, DateTime, JSON, Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.session import Base


class CreditScore(Base):
    __tablename__ = "credit_scores"

    id      = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # ── Score output ──────────────────────────────────────────────────────────
    score       = Column(Integer, nullable=False)          # 300–850 (credit bureau convention)
    risk_level  = Column(String,  nullable=False)          # "trusted" | "moderate" | "risky"

    # ── Raw signals (0–100 normalised) ────────────────────────────────────────
    income_level      = Column(Float, nullable=True)       # total income normalised
    income_stability  = Column(Float, nullable=True)       # 100 - normalised std-dev of monthly income
    savings_rate      = Column(Float, nullable=True)       # (income - expenses) / income × 100
    activity          = Column(Float, nullable=True)       # tx count per month normalised
    burden            = Column(Float, nullable=True)       # expenses / income × 100

    # ── Rich output ───────────────────────────────────────────────────────────
    insights              = Column(JSON, nullable=True)    # List[str] — rule-based explanations
    transactions_summary  = Column(JSON, nullable=True)    # {income, expenses, net, top_categories}

    # ── Provenance ────────────────────────────────────────────────────────────
    upload_id         = Column(String, nullable=True)      # which upload triggered this computation
    transaction_count = Column(Integer, nullable=True)     # how many rows were used
    data_quality      = Column(String, nullable=True)      # "good" | "low_data" | "insufficient"

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    is_active   = Column(Boolean, nullable=False, default=True)   # only one active per user
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ── Relationships ─────────────────────────────────────────────────────────
    user = relationship("User", back_populates="credit_scores")

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_credit_score_user_active", "user_id", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<CreditScore id={self.id} user={self.user_id} "
            f"score={self.score} risk={self.risk_level} active={self.is_active}>"
        )
