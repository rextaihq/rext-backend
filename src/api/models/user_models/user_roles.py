import uuid
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from datetime import datetime,timezone
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


# -------------------------
# UserRole
# -------------------------
class UserRole(Base, SerializableMixin):
    __tablename__ = "user_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=True)
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    is_primary = Column(Boolean, default=True)
    assigned_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    user = relationship("Users", foreign_keys=[user_id], back_populates="user_roles")
    role = relationship("Role", foreign_keys=[role_id], back_populates="user_roles")
    workspace = relationship("WorkspaceModel", foreign_keys=[workspace_id], back_populates="user_roles")
    assigned_by = relationship("Users", foreign_keys=[assigned_by_user_id], back_populates="assigned_roles")

    # to_dict() inherited from SerializableMixin