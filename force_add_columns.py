import asyncio
import os
import asyncpg
from dotenv import load_dotenv

async def main():
    load_dotenv()
    uri = os.getenv('POSTGRES_URI_CUSTOM')
    if '+asyncpg' in uri:
        uri = uri.replace('+asyncpg', '')
    if '+psycopg' in uri:
        uri = uri.replace('+psycopg', '')
    if '+psycopg2' in uri:
        uri = uri.replace('+psycopg2', '')
        
    conn = await asyncpg.connect(uri)
    
    try:
        await conn.execute("ALTER TABLE content ADD COLUMN IF NOT EXISTS shopify_article_id BIGINT;")
        await conn.execute("ALTER TABLE content ADD COLUMN IF NOT EXISTS shopify_article_url TEXT;")
        await conn.execute("ALTER TABLE content ADD COLUMN IF NOT EXISTS shopify_published_at TIMESTAMP WITH TIME ZONE;")
        print("Successfully added Shopify columns to the content table.")
        
        # Make sure alembic_version points to the new head just in case
        await conn.execute("UPDATE alembic_version SET version_num = 'cb4411f82bc5'")
        print("Database marked as being at alembic revision cb4411f82bc5")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
