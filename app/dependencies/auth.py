from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.firebase import verify_firebase_token
from app.dependencies.db import get_db
from app.models.user import User as UserModel
from app.core.logger import get_logger

logger = get_logger(__name__)
security = HTTPBearer()

async def get_current_user(
    res: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> UserModel:
    token = res.credentials
    decoded_token = verify_firebase_token(token)
    
    if not decoded_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    firebase_uid = decoded_token.get("uid")
    user = db.query(UserModel).filter(UserModel.firebase_uid == firebase_uid).first()
    
    if not user:
        # For simplicity in hackathon, we might want to auto-create user or just fail
        # Usually, the auth_service handles the first-time creation.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user
