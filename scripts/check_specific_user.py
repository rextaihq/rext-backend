import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.users import Users
from src.api.models.admin_models.admin_invitations import PlatformAdminInvitations


async def check_user_subscription():
    database_url = os.getenv("POSTGRES_URI_CUSTOM") or os.getenv("DATABASE_URL")
    
    # Fix protocol for asyncpg
    if "postgresql+psycopg://" in database_url:
        database_url = database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://")
    
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    user_id = "df538ecc-143a-4e2b-9284-c8fca1743b4a"

    async with async_session() as db:
        print(f"Checking subscription for user: {user_id}")
        
        # Check if user exists
        user_result = await db.execute(select(Users).where(Users.id == user_id))
        user = user_result.scalar_one_or_none()
        
        if user:
            print(f"✅ User found: {user.email}")
        else:
            print("❌ User NOT found in database")

        # Check subscription
        sub_result = await db.execute(select(UserSubscription).where(UserSubscription.user_id == user_id))
        subscription = sub_result.scalar_one_or_none()
        
        if subscription:
            print(f"✅ Subscription found: ID={subscription.id}, Status={subscription.status}, Plan={subscription.plan_id}")
        else:
            print("❌ No subscription found for this user.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_user_subscription())
