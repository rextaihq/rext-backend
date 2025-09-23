from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.api.database.database import Base
import uuid


class ContentUsers(Base):
    __tablename__ = "reviewers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)

    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    expertise = Column(JSONB, nullable=True)
    affiliated_topics = Column(JSONB, nullable=True)

    # ✅ Auto timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "email": self.email,
            "expertise": self.expertise,
            "affiliated_topics": self.affiliated_topics,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }