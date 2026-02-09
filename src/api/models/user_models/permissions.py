from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)
    # Relationships
    roles = relationship("RolePermission", back_populates="permission")

    # to_dict() inherited from SerializableMixin