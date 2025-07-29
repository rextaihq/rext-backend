from sqlalchemy import Column, Integer, String, Boolean
from src.api.database.database import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid

class User(Base):
    __tablename__ = "users"
    iid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    username = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)


class Workflow(Base):
    __tablename__ = "workflows"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    thread_id = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    status = Column(String, default="pending")
