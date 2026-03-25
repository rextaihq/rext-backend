import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def run_diagnostics():
    db_url = os.getenv("POSTGRES_URI_CUSTOM")
    if not db_url:
        print("POSTGRES_URI_CUSTOM not found in .env")
        return

    # asyncpg expects postgresql:// not postgresql+asyncpg://
    if db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql+asyncpg", "postgresql")

    print(f"Connecting to database...")
    conn = await asyncpg.connect(db_url)
    try:
        print("\nChecking alembic_version table:")
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"- Version in DB: {version}")

        print("\nChecking notifications table columns:")
        columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'notifications'
        """)
        for col in columns:
            print(f"- {col['column_name']} ({col['data_type']})")

        print("\nChecking notifications table indexes:")
        indexes = await conn.fetch("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'notifications'
        """)
        for idx in indexes:
            print(f"- {idx['indexname']}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
