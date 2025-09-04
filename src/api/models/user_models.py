from sqlalchemy import Column, Integer, String, Boolean
from src.api.database.database import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    username = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
