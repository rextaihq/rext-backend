import uuid
from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from src.api.database.database import Base
from src.api.models.base import SerializableMixin

# -------------------------
# Workspace Members
# -------------------------
class WorkspaceMembers(Base, SerializableMixin):
    __tablename__ = "workspace_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=False)
    invitation_id = Column(UUID(as_uuid=True), ForeignKey("user_invitations.id"), nullable=True)
    status = Column(String(50), default="pending")  # active, inactive, pending
    is_default = Column(Boolean, default=False)
    joined_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    last_activity_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("Users", foreign_keys=[user_id], back_populates="workspace_memberships")
    workspace = relationship("WorkspaceModel", foreign_keys=[workspace_id], back_populates="members")
    invitation = relationship("UserInvitations", foreign_keys=[invitation_id], back_populates="workspace_members")

    # to_dict() inherited from SerializableMixin