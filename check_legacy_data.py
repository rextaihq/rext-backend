
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

async def check_leftover_placeholders():
    db_url = os.getenv("POSTGRES_URI_CUSTOM")
    if not db_url:
        print("POSTGRES_URI_CUSTOM not found")
        return

    if not db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM users WHERE password_hash = 'oauth_no_password'"))
            count = result.scalar()
            print(f"Count of leftover 'oauth_no_password': {count}")
            
            result = await conn.execute(text("SELECT COUNT(*) FROM users WHERE password_hash IS NULL"))
            null_count = result.scalar()
            print(f"Count of NULL password_hash: {null_count}")
        await engine.dispose()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_leftover_placeholders())
