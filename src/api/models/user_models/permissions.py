from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


# -------------------------
# Permissions Model
# -------------------------
class Permission(Base, SerializableMixin):
    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    display_name = Column(String(200))
    description = Column(Text)
    resource = Column(String(50))
    action = Column(String(50))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    # Relationships
    roles = relationship("RolePermission", back_populates="permission")

    # to_dict() inherited from SerializableMixin