import asyncio
from sqlalchemy import text
from app.database.session import engine

async def add_missing_columns():
    async with engine.begin() as conn:
        print("Adding missing columns to kyc_records table...")
        try:
            await conn.execute(text("ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS full_name VARCHAR;"))
            await conn.execute(text("ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS dob VARCHAR;"))
            await conn.execute(text("ALTER TABLE kyc_records ADD COLUMN IF NOT EXISTS gender VARCHAR;"))
            print("Successfully added columns.")
        except Exception as e:
            print(f"Error adding columns: {e}")

if __name__ == "__main__":
    asyncio.run(add_missing_columns())
