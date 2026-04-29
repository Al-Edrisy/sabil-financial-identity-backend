from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.wallet import Wallet
from app.core.logger import get_logger

logger = get_logger(__name__)

class WalletService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_wallet(self, user_id: int, for_update: bool = False) -> Wallet:
        stmt = select(Wallet).where(Wallet.user_id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_balance(self, user_id: int, amount: float):
        """
        Increment or decrement balance (Asynchronous).
        """
        wallet = await self.get_wallet(user_id)
        if not wallet:
            logger.error(f"Wallet not found for user_id: {user_id}")
            return False
            
        wallet.balance += amount
        self.db.add(wallet)
        return True

    async def check_funds(self, user_id: int, amount: float) -> bool:
        wallet = await self.get_wallet(user_id)
        if not wallet:
            return False
        return wallet.balance >= amount
