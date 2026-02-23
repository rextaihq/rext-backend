import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_alembic_version():
    db_url = os.getenv("POSTGRES_URI_CUSTOM")
    if not db_url:
        print("POSTGRES_URI_CUSTOM not found in .env")
        return

    if db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql+asyncpg", "postgresql")

    print(f"Connecting to database...")
    conn = await asyncpg.connect(db_url)
    try:
        current_version = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"Current version in DB: {current_version}")
        
        target_version = '572a638e2089'
        print(f"Updating version to: {target_version}")
        
        await conn.execute("UPDATE alembic_version SET version_num = $1", target_version)
        print("Update successful!")
        
        new_version = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"New version in DB: {new_version}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_alembic_version())
