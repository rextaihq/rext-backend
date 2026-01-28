import asyncio
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.api.database.async_database import async_engine
from sqlalchemy import inspect

async def check_tables():
    async with async_engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        print("Tables in database:")
        for table in sorted(tables):
            print(f" - {table}")

if __name__ == "__main__":
    asyncio.run(check_tables())
