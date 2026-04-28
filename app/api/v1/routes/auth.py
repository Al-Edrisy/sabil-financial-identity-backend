from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.dependencies.db import get_db
from app.services.auth_service import AuthService
from app.schemas.user import User as UserSchema

router = APIRouter()

@router.post("/login", response_model=UserSchema)
async def login(
    id_token: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    service = AuthService(db)
    user = service.authenticate_user(id_token)
    return user
