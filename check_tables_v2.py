import asyncio
import sys
import os

# Add src to path
sys.path.append(os.getcwd())

from src.api.database.async_database import async_engine
from sqlalchemy import inspect

async def check_tables():
    async with async_engine.connect() as conn:
        def get_tables(sync_conn):
            # Get table names
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            return tables

        tables = await conn.run_sync(get_tables)
        print("TABLE_LIST_START")
        for table in sorted(tables):
            print(table)
        print("TABLE_LIST_END")

if __name__ == "__main__":
    asyncio.run(check_tables())
