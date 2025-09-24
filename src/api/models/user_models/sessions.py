import uuid
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from datetime import datetime
from src.api.database.database import Base

class UserRole(Base):
    __tablename__ = "sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    session_token = Column(String(255), unique=True, nullable=False)
    refresh_token = Column(String(255), unique=True, nullable=False)
    device_info = Column(JSONB)
    ip_address = Column(INET)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    last_activity_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(TIMESTAMP, nullable=False)


    # Make a relationship to the User model
    user = relationship("User", backref="sessions")