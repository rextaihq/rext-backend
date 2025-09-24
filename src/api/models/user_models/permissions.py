from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from src.api.database.database import Base


# -------------------------
# Role
# -------------------------
class Role(Base):
    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    resource = Column(String(100))
    action = Column(String(50))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "resource": self.resource,
            "action": self.action,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }