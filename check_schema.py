
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

async def check_schema():
    db_url = os.getenv("POSTGRES_URI_CUSTOM")
    if not db_url:
        print("POSTGRES_URI_CUSTOM not found")
        return

    if not db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT column_name, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'password_hash'
            """))
            row = result.fetchone()
            if row:
                print(f"Column: {row[0]}, Nullable: {row[1]}")
            else:
                print("Column password_hash not found in users table")
        await engine.dispose()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_schema())
