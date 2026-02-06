
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

async def force_alembic_version():
    db_url = os.getenv("POSTGRES_URI_CUSTOM")
    if not db_url:
        print("POSTGRES_URI_CUSTOM not found")
        return

    if not db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    target_version = 'd499a5520245' # Parent of the f23456789abc migration

    try:
        engine = create_async_engine(db_url)
        async with engine.begin() as conn:
            # First check if table exists
            await conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
            
            # Delete existing
            await conn.execute(text("DELETE FROM alembic_version"))
            
            # Insert target
            await conn.execute(text(f"INSERT INTO alembic_version (version_num) VALUES ('{target_version}')"))
            print(f"✅ Successfully stamped database as {target_version}")
        await engine.dispose()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(force_alembic_version())
