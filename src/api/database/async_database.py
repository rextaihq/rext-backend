from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from dotenv import load_dotenv
import os
from src.utils.logger import logger

# Load environment variables
load_dotenv()

# Get database URL and convert to async URL
SQLALCHEMY_DATABASE_URL = os.getenv("POSTGRES_URI_CUSTOM")

# Convert postgresql:// to postgresql+asyncpg://
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
else:
    ASYNC_DATABASE_URL = SQLALCHEMY_DATABASE_URL

logger.info("Async database configuration initialized", extra={"database_url": ASYNC_DATABASE_URL.split("@")[-1] if ASYNC_DATABASE_URL else None})

# Create async engine
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    pool_pre_ping=True,  # Verify connections before using
    pool_size=20,  # Connection pool size
    max_overflow=10,  # Max connections beyond pool_size
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Async dependency for FastAPI
async def get_async_db():
    """Async database session dependency for FastAPI routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
