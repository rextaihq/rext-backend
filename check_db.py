import asyncio
import os

import asyncpg
from dotenv import load_dotenv


async def main():
    load_dotenv()
    uri = os.getenv("POSTGRES_URI_CUSTOM")
    uri = uri.replace("+asyncpg", "").replace("+psycopg", "").replace("+psycopg2", "")

    conn = await asyncpg.connect(uri)
    val = await conn.fetchval("SELECT version_num FROM alembic_version")
    print(f"DB VERSION: {val}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
