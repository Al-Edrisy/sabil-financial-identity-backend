from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from app.dependencies.db import get_db
from app.dependencies.auth import get_current_user
from app.services.kyc_service import KYCService
from app.schemas.kyc import KYCResponse
from app.models.user import User

router = APIRouter()

@router.post("/verify", response_model=KYCResponse)
async def verify_kyc(
    id_card: UploadFile = File(...),
    selfie: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = KYCService(db)
    result = await service.process_kyc(current_user.id, id_card, selfie)
    return result

@router.get("/status", response_model=KYCResponse)
async def get_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = KYCService(db)
    status = service.get_kyc_status(current_user.id)
    return status
