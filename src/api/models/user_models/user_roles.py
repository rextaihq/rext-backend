import uuid
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from datetime import datetime
from src.api.database.database import Base

class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    # workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=True)

    is_primary = Column(Boolean, default=False)
    assigned_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="user_roles")
    role = relationship("Role", backref="user_roles")
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])


    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "role_id": str(self.role_id),
            "is_primary": self.is_primary,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "assigned_by_user_id": str(self.assigned_by_user_id) if self.assigned_by_user_id else None,
        }