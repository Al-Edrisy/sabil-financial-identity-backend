from sqlalchemy.orm import Session
from app.models.user import User
from app.models.wallet import Wallet
from app.core.firebase import verify_firebase_token
from fastapi import HTTPException, status

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def authenticate_user(self, id_token: str):
        decoded_token = verify_firebase_token(id_token)
        if not decoded_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Firebase token",
            )
        
        firebase_uid = decoded_token.get("uid")
        email = decoded_token.get("email")
        
        user = self.db.query(User).filter(User.firebase_uid == firebase_uid).first()
        
        if not user:
            # Create user if it doesn't exist
            user = User(
                firebase_uid=firebase_uid,
                email=email,
                full_name=decoded_token.get("name", "")
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            
            # Create default wallet for new user
            wallet = Wallet(user_id=user.id, balance=0.0, currency="USD")
            self.db.add(wallet)
            self.db.commit()
            
        return user

auth_service = None # Dependency will instantiate this
