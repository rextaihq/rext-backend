from sqlalchemy import Column, Integer, String, Boolean
from src.api.database.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)


class Workflow(Base):
    __tablename__ = "workflows"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    thread_id = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    status = Column(String, default="pending")