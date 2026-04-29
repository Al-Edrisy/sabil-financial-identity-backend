"""
app/models/user.py — Core user account model.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, SmallInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.session import Base


class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    firebase_uid = Column(String, unique=True, index=True, nullable=True)   # nullable: phone-only users may not have Firebase UID yet
    email        = Column(String, unique=True, index=True, nullable=True)   # nullable: phone-only users
    phone_number = Column(String, unique=True, index=True, nullable=True)   # nullable until verified
    country_code = Column(String(4), nullable=True)                         # ISO country code e.g. "YE", "SA"
    full_name    = Column(String, nullable=True)
    is_active    = Column(Boolean, default=True, nullable=False)
    is_admin     = Column(Boolean, default=False, nullable=False)

    # ── Onboarding state ──────────────────────────────────────────────────────
    # 0 = phone entered (not verified)
    # 1 = phone verified / account created
    # 2 = KYC submitted (pending/verified/rejected)
    # 3 = financial documents uploaded
    onboarding_step = Column(SmallInteger, default=0, nullable=False)
    phone_verified  = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ── Relationships ─────────────────────────────────────────────────────────
    wallet = relationship(
        "Wallet",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    kyc_records = relationship(
        "KYC",
        back_populates="user",
        foreign_keys="[KYC.user_id]",
        cascade="all, delete-orphan",
        order_by="KYC.created_at.desc()",
    )

    sent_transactions = relationship(
        "Transaction",
        foreign_keys="[Transaction.sender_id]",
        back_populates="sender",
    )
    received_transactions = relationship(
        "Transaction",
        foreign_keys="[Transaction.receiver_id]",
        back_populates="receiver",
    )

    parsed_transactions = relationship(
        "ParsedTransaction",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    credit_scores = relationship(
        "CreditScore",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="CreditScore.computed_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} phone={self.phone_number} step={self.onboarding_step}>"
