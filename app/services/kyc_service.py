from sqlalchemy.orm import Session
from app.models.kyc import KYC, KYCStatus
from app.models.user import User
from fastapi import UploadFile, File

class KYCService:
    def __init__(self, db: Session):
        self.db = db

    async def process_kyc(self, user_id: int, id_card: UploadFile, selfie: UploadFile):
        # 1. OCR Extraction (Mock for now)
        # 2. Face Matching (Mock for now)
        # 3. Save Record
        
        kyc_record = self.db.query(KYC).filter(KYC.user_id == user_id).first()
        
        if not kyc_record:
            kyc_record = KYC(user_id=user_id)
            self.db.add(kyc_record)
        
        # Simulating AI processing
        kyc_record.status = KYCStatus.VERIFIED
        kyc_record.id_type = "passport"
        kyc_record.id_number = "A1234567"
        kyc_record.ocr_data = {"name": "John Doe", "expiry": "2030-01-01"}
        kyc_record.face_match_score = 0.98
        
        self.db.commit()
        self.db.refresh(kyc_record)
        return kyc_record

    def get_kyc_status(self, user_id: int):
        return self.db.query(KYC).filter(KYC.user_id == user_id).first()
