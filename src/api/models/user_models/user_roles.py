from sqlalchemy import Column, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin


# -------------------------
# UserRole
# -------------------------
class UserRole(Base, SerializableMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "user_roles"

    # id provided by mixin
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=True)
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    is_primary = Column(Boolean, default=True)
    assigned_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', 'workspace_id', name='uq_user_role_workspace'),
    )

    # Relationships
    user = relationship("Users", foreign_keys=[user_id], back_populates="user_roles")
    role = relationship("Role", foreign_keys=[role_id], back_populates="user_roles")
    workspace = relationship("WorkspaceModel", foreign_keys=[workspace_id], back_populates="user_roles")
    assigned_by = relationship("Users", foreign_keys=[assigned_by_user_id], back_populates="assigned_roles")

    # to_dict() inherited from SerializableMixin