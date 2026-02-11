import asyncio
import os
from sqlalchemy import text
from src.api.database.async_database import async_engine
from dotenv import load_dotenv

load_dotenv()

async def verify_encryption():
    engine = async_engine
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT app_password, api_key FROM integrations WHERE app_password IS NOT NULL OR api_key IS NOT NULL LIMIT 5"))
        rows = result.fetchall()
        if not rows:
            print("No integration credentials found to verify.")
            return
            
        for i, row in enumerate(rows):
            app_pass = row[0]
            api_key = row[1]
            print(f"Row {i+1}:")
            if app_pass:
                print(f"  app_password starts with 'gAAAA': {app_pass.startswith('gAAAA')}")
            if api_key:
                print(f"  api_key starts with 'gAAAA': {api_key.startswith('gAAAA')}")
                
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_encryption())
