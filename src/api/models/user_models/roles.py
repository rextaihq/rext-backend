from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


# -------------------------
# Roles
# -------------------------
class Role(Base, SerializableMixin):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    display_name = Column(String(150), nullable=False)
    description = Column(Text)
    hierarchy_level = Column(Integer, default=0)

    # Role Classification:
    # - is_system_role: Platform-level roles (super_admin, admin, user)
    # - is_workspace_role: Can be assigned to workspace members (workspace_owner, editor, etc.)
    is_system_role = Column(Boolean, default=False)
    is_workspace_role = Column(Boolean, default=False, nullable=False)

    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    permissions = relationship("RolePermission", back_populates="role")
    user_roles = relationship("UserRole", back_populates="role")
    invited_roles = relationship("UserInvitations", back_populates="role")

    # to_dict() inherited from SerializableMixin