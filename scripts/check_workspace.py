
import asyncio
from sqlalchemy import select
from uuid import UUID
from src.api.database.async_database import get_async_db_context
from src.api.models.knowledge_models.persona_model import Persona
from src.api.models.knowledge_models.knowledge_model import BrandVoice

async def check_db():
    workspace_id = UUID("dfcdd331-ec59-47d7-b5e2-8488748cd501")
    async with get_async_db_context() as db:
        # Check BrandVoice
        result = await db.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace_id))
        bv = result.scalar_one_or_none()
        if bv:
            print(f"BrandVoice found: {bv.about[:100]}...")
        else:
            print("BrandVoice not found for workspace.")

        # Check Personas
        result = await db.execute(select(Persona).where(Persona.workspace_id == workspace_id))
        personas = result.scalars().all()
        print(f"Found {len(personas)} personas.")
        for p in personas:
            print(f" - {p.name} ({p.professional_title})")

if __name__ == "__main__":
    asyncio.run(check_db())
