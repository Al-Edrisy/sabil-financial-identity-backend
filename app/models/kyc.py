from sqlalchemy import Column, Integer, String, Enum, ForeignKey, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.database.session import Base

class KYCStatus(enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"

class KYC(Base):
    __tablename__ = "kyc_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    status = Column(Enum(KYCStatus), default=KYCStatus.PENDING)
    id_type = Column(String)
    id_number = Column(String)
    ocr_data = Column(JSON) # Extracted data from OCR
    face_match_score = Column(Float)
    id_image_url = Column(String)
    selfie_image_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="kyc")
