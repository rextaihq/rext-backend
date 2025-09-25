import uuid
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from datetime import datetime
from src.api.database.database import Base


# -------------------------
# UserRole
# -------------------------
class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=True)
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    is_primary = Column(Boolean, default=True)
    assigned_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("Users", foreign_keys=[user_id], back_populates="user_roles")
    role = relationship("Role", foreign_keys=[role_id], back_populates="user_roles")
    workspace = relationship("WorkspaceModel", foreign_keys=[workspace_id], back_populates="user_roles")
    assigned_by = relationship("Users", foreign_keys=[assigned_by_user_id], back_populates="assigned_roles")

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "role_id": str(self.role_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "is_primary": self.is_primary,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
        }