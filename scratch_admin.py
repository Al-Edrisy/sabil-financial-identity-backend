import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.models.user import User

# Hardcode 127.0.0.1 to avoid localhost resolution issues
db_url = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/sabil"
engine = create_async_engine(db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession)

async def main():
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.email == "salehfree33@gmail.com")
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            print(f"Found user: {user.email} (ID: {user.id})")
            user.is_admin = True
            await session.commit()
            print("Successfully updated user to admin.")
        else:
            print("User not found by email.")
            new_user = User(
                email="salehfree33@gmail.com",
                is_admin=True,
                is_active=True
            )
            session.add(new_user)
            await session.commit()
            print("Created user 'salehfree33@gmail.com' and set as admin.")

if __name__ == "__main__":
    asyncio.run(main())
