"""
app/models/transaction.py — Wallet transaction ledger.
"""

import enum
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.session import Base


class TransactionType(enum.Enum):
    TRANSFER = "transfer"
    TOPUP    = "topup"
    WITHDRAW = "withdraw"


class TransactionStatus(enum.Enum):
    PENDING   = "pending"
    COMPLETED = "completed"
    FAILED    = "failed"


class Transaction(Base):
    __tablename__ = "transactions"

    id               = Column(Integer, primary_key=True, index=True)
    sender_id        = Column(Integer, ForeignKey("users.id"), nullable=True)
    receiver_id      = Column(Integer, ForeignKey("users.id"), nullable=True)
    amount           = Column(Float, nullable=False)
    currency         = Column(String, nullable=False)       # original send currency
    fx_rate          = Column(Float, default=1.0, nullable=False)
    converted_amount = Column(Float, nullable=False)
    target_currency  = Column(String, nullable=False)
    type             = Column(Enum(TransactionType), nullable=False)
    status           = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    reference        = Column(String, unique=True, index=True)
    description      = Column(String, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Use back_populates (not backref) — User model declares the other side explicitly
    sender   = relationship("User", foreign_keys=[sender_id],   back_populates="sent_transactions")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_transactions")

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} ref={self.reference} "
            f"type={self.type.value} amount={self.amount} {self.currency} "
            f"status={self.status.value}>"
        )
