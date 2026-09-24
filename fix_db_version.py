import asyncio
import os

import asyncpg
from dotenv import load_dotenv


async def main():
    load_dotenv()
    uri = os.getenv("POSTGRES_URI_CUSTOM")
    uri = uri.replace("+asyncpg", "").replace("+psycopg", "").replace("+psycopg2", "")

    conn = await asyncpg.connect(uri)

    # Check current version
    val = await conn.fetchval("SELECT version_num FROM alembic_version")
    print(f"Current DB VERSION: {val}")

    # Update to inv003
    await conn.execute("UPDATE alembic_version SET version_num = 'inv003'")
    print("Updated DB VERSION to: inv003")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
