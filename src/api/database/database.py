from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.api.config import get_settings
from src.api.database.base import Base

# Get settings instance
settings = get_settings()

SQLALCHEMY_DATABASE_URL = settings.POSTGRES_URI_CUSTOM

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()