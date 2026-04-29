import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from fastapi import HTTPException, status
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.user import User
from app.services.wallet_service import WalletService
from app.utils.fx import convert_currency
from app.core.logger import get_logger

logger = get_logger(__name__)

class TransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.wallet_service = WalletService(db)

    async def transfer_funds(self, sender_id: int, receiver_email: str, amount: float, currency: str):
        """
        Execute a fund transfer between users (Asynchronous).
        """
        result = await self.db.execute(select(User).where(User.email == receiver_email))
        receiver = result.scalar_one_or_none()
        
        if not receiver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found")
        
        if sender_id == receiver.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot transfer to yourself")

        # Use FOR UPDATE to lock wallet rows during transaction to prevent race conditions
        sender_wallet = await self.wallet_service.get_wallet(sender_id, for_update=True)
        if not sender_wallet:
            raise HTTPException(status_code=404, detail="Sender wallet not found")
            
        if sender_wallet.balance < amount:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

        receiver_wallet = await self.wallet_service.get_wallet(receiver.id, for_update=True)
        if not receiver_wallet:
            raise HTTPException(status_code=404, detail="Receiver wallet not found")
        
        target_amount, rate = convert_currency(amount, sender_wallet.currency, receiver_wallet.currency)

        try:
            await self.wallet_service.update_balance(sender_id, -amount)
            await self.wallet_service.update_balance(receiver.id, target_amount)
            
            tx_ref = f"TX-{uuid.uuid4().hex[:8].upper()}"
            transaction = Transaction(
                sender_id=sender_id,
                receiver_id=receiver.id,
                amount=amount,
                currency=sender_wallet.currency,
                fx_rate=rate,
                converted_amount=target_amount,
                target_currency=receiver_wallet.currency,
                type=TransactionType.TRANSFER,
                status=TransactionStatus.COMPLETED,
                reference=tx_ref,
                description=f"Transfer to {receiver_email}"
            )
            self.db.add(transaction)
            await self.db.commit()
            await self.db.refresh(transaction)
            
            logger.info(f"Transfer successful: {tx_ref}")
            return transaction

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Transfer failed: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Transfer failed")

    async def transfer_funds_by_id(self, from_user_id: int, to_user_id: int, amount: float, description: str = None):
        result = await self.db.execute(select(User).where(User.id == to_user_id))
        receiver = result.scalar_one_or_none()
        if not receiver:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver not found")
        
        sender_wallet = await self.wallet_service.get_wallet(from_user_id)
        # Use the sender's actual wallet currency instead of hardcoding USD
        currency = sender_wallet.currency if sender_wallet else "USD"
        return await self.transfer_funds(from_user_id, receiver.email, amount, currency)

    async def withdraw_funds(self, user_id: int, amount: float, description: str = "Wallet Withdrawal"):
        """Executes a wallet withdrawal transaction (Asynchronous)."""
        wallet = await self.wallet_service.get_wallet(user_id, for_update=True)
        if not wallet or wallet.balance < amount:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")
        
        try:
            await self.wallet_service.update_balance(user_id, -amount)
            
            tx_ref = f"WD-{uuid.uuid4().hex[:8].upper()}"
            transaction = Transaction(
                sender_id=user_id,
                receiver_id=None,
                amount=amount,
                currency=wallet.currency,
                fx_rate=1.0,
                converted_amount=amount,
                target_currency=wallet.currency,
                type=TransactionType.WITHDRAW,
                status=TransactionStatus.COMPLETED,
                reference=tx_ref,
                description=description
            )
            self.db.add(transaction)
            await self.db.commit()
            await self.db.refresh(transaction)
            return transaction
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Withdrawal failed")

    async def get_transaction_by_id(self, user_id: int, tx_id: int):
        result = await self.db.execute(select(Transaction).where(Transaction.id == tx_id))
        tx = result.scalar_one_or_none()
        if not tx:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
        if tx.sender_id != user_id and tx.receiver_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return tx

    async def get_history(self, user_id: int):
        result = await self.db.execute(
            select(Transaction).where(
                or_(Transaction.sender_id == user_id, Transaction.receiver_id == user_id)
            ).order_by(Transaction.created_at.desc())
        )
        return result.scalars().all()

    async def top_up(self, user_id: int, amount: float):
        wallet = await self.wallet_service.get_wallet(user_id)
        await self.wallet_service.update_balance(user_id, amount)
        
        tx_ref = f"TP-{uuid.uuid4().hex[:8].upper()}"
        transaction = Transaction(
            sender_id=None,
            receiver_id=user_id,
            amount=amount,
            currency=wallet.currency,
            fx_rate=1.0,
            converted_amount=amount,
            target_currency=wallet.currency,
            type=TransactionType.TOPUP,
            status=TransactionStatus.COMPLETED,
            reference=tx_ref,
            description="Wallet Top-up"
        )
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction
