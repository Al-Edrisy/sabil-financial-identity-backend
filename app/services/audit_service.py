from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Any
from app.models.audit import AuditLog
from app.core.logger import get_logger

logger = get_logger(__name__)

class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(
        self,
        action: str,
        user_id: Optional[int] = None,
        status: str = "SUCCESS",
        metadata: Optional[Any] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """
        Record a sensitive action in the audit log (Asynchronous).
        """
        try:
            audit_entry = AuditLog(
                user_id=user_id,
                action=action,
                status=status,
                metadata_json=metadata,
                ip_address=ip_address,
                user_agent=user_agent
            )
            self.db.add(audit_entry)
            await self.db.commit()
            logger.info(f"Audit Log: User {user_id} performed {action} - Status: {status}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to record audit log: {e}")
