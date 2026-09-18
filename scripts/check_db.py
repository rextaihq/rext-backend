import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()


async def main():
    db_url = os.getenv("POSTGRES_URI_CUSTOM")
    if not db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT id, email FROM users"))
        print(f"Users: {result.fetchall()}")
        result = await conn.execute(text("SELECT id, slug FROM workspace"))
        print(f"Workspaces: {result.fetchall()}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
