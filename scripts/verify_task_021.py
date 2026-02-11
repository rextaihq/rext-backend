import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import insert
from src.api.models.user_models.roles import Role
from src.api.config import get_settings

settings = get_settings()

async def verify_constraint():
    engine = create_async_engine(settings.database_url.replace("postgresql://", "postgresql+asyncpg://"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Create a role (should succeed)
        unique_name = f"test_role_{uuid.uuid4().hex[:8]}"
        print(f"Creating role: {unique_name}")
        
        role1 = Role(
            name=unique_name,
            display_name="Test Role 1",
            created_at=datetime.now(timezone.utc)
        )
        session.add(role1)
        await session.commit()
        print("First role created successfully.")

        # 2. Try to create duplicate (should fail)
        print(f"Attempting to create duplicate role: {unique_name}")
        role2 = Role(
            name=unique_name,
            display_name="Test Role 2 (Duplicate)",
            created_at=datetime.now(timezone.utc)
        )
        session.add(role2)
        try:
            await session.commit()
            print("ERROR: Duplicate role created! Constraint missed.")
        except Exception as e:
            print(f"SUCCESS: Caught expected exception: {type(e).__name__}")
            # print(e)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_constraint())
