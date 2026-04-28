from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    firebase_uid: str

class UserUpdate(UserBase):
    is_active: Optional[bool] = None

class UserInDBBase(UserBase):
    id: int
    firebase_uid: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class User(UserInDBBase):
    pass
