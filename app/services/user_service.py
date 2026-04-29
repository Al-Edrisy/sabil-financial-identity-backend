from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from typing import List, Optional
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.core.logger import get_logger

logger = get_logger(__name__)

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _populate_user_attributes(self, user: User) -> User:
        """Manually populates transient attributes for the User schema."""
        if not user:
            return user

        # Wallet balance
        user.wallet_balance = getattr(user.wallet, 'balance', 0.0) if hasattr(user, 'wallet') else 0.0

        # KYC status
        user.kyc_status = "not_started"
        if hasattr(user, 'kyc_records') and user.kyc_records:
            active = next((r for r in user.kyc_records if r.is_active), user.kyc_records[0])
            user.kyc_status = active.status.value

        # Credit score (latest active)
        user.credit_score = None
        if hasattr(user, 'credit_scores') and user.credit_scores:
            active_score = next((s for s in user.credit_scores if s.is_active), None)
            if active_score:
                user.credit_score = active_score.score

        return user

    async def get_user(self, user_id: int) -> Optional[User]:
        stmt = select(User).where(User.id == user_id).options(
            joinedload(User.wallet),
            joinedload(User.kyc_records),
            joinedload(User.credit_scores),
        )
        result = await self.db.execute(stmt)
        user = result.unique().scalar_one_or_none()
        return self._populate_user_attributes(user)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email).options(
            joinedload(User.wallet),
            joinedload(User.kyc_records),
            joinedload(User.credit_scores),
        )
        result = await self.db.execute(stmt)
        user = result.unique().scalar_one_or_none()
        return self._populate_user_attributes(user)

    async def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[User]:
        stmt = select(User).where(User.firebase_uid == firebase_uid).options(
            joinedload(User.wallet),
            joinedload(User.kyc_records),
            joinedload(User.credit_scores),
        )
        result = await self.db.execute(stmt)
        user = result.unique().scalar_one_or_none()
        return self._populate_user_attributes(user)

    async def get_users(
        self,
        skip: int = 0,
        limit: int = 100,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[User]:
        stmt = select(User)
        if email:
            stmt = stmt.where(User.email.ilike(f"%{email}%"))
        if phone:
            stmt = stmt.where(User.phone_number.ilike(f"%{phone}%"))
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            
        stmt = stmt.options(joinedload(User.wallet), joinedload(User.kyc_records))
        result = await self.db.execute(stmt.offset(skip).limit(limit))
        users = result.scalars().unique().all()
        return [self._populate_user_attributes(u) for u in users]

    async def create_user(self, user_in: UserCreate) -> User:
        db_user = User(
            firebase_uid=user_in.firebase_uid,
            email=user_in.email,
            phone_number=user_in.phone_number,
            full_name=user_in.full_name,
            is_active=True
        )
        self.db.add(db_user)
        await self.db.flush()
        await self.db.refresh(db_user)
        return db_user

    async def update_user(self, user_id: int, user_in: UserUpdate) -> Optional[User]:
        db_user = await self.get_user(user_id)
        if not db_user:
            return None
        
        update_data = user_in.model_dump(exclude_unset=True)
        for field in update_data:
            setattr(db_user, field, update_data[field])
            
        self.db.add(db_user)
        await self.db.flush()
        await self.db.refresh(db_user)
        return db_user

    async def delete_user(self, user_id: int) -> bool:
        db_user = await self.get_user(user_id)
        if not db_user:
            return False
        await self.db.delete(db_user)
        await self.db.commit()
        return True
