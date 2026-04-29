from typing import AsyncGenerator
from app.database.session import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to provide a non-blocking database session to routes.
    Ensures the session is correctly closed after the request lifecycle.
    """
    async with AsyncSessionLocal() as session:
        yield session
