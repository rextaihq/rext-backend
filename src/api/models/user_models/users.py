from sqlalchemy import Column, String
from src.api.database.database import Base
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Users(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    display_name = Column(String(200))
    password_changed_at = Column(TIMESTAMP)
    locked_until = Column(TIMESTAMP)
    reset_token = Column(String(255))
    reset_token_expires = Column(TIMESTAMP)
    avatar_url = Column(Text)
    status = Column(String(20), default="active")
    email_verified = Column(Boolean, default=False)
    email_verified_at = Column(TIMESTAMP)
    last_login_at = Column(TIMESTAMP)
    login_count = Column(Integer, default=0)
    failed_login_attempts = Column(Integer, default=0)
    language = Column(String(10), default="en")
    timezone = Column(String(50), default="UTC")
    created_at = Column(TIMESTAMP, nullable=False,default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(TIMESTAMP)


    # define the relations
    

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "display_name": self.display_name,
            "status": self.status,
            "email_verified": self.email_verified,
            "language": self.language,
            "timezone": self.timezone,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }