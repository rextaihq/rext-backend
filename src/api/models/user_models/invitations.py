from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin

class UserInvitations(Base, SerializableMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "user_invitations"
    
    # id provided by mixin
    email = Column(String(255), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    invitation_token = Column(String(255), unique=True, nullable=False)
    status = Column(String(50), default="pending")  # e.g., pending, accepted, revoked
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)
    reminder_sent = Column(Boolean, default=False, nullable=False)  # Track if expiry reminder email sent

    # add a constraint to ensure that the combination of email and workspace_id is unique
    __table_args__ = (
        UniqueConstraint('email', 'workspace_id', name='uq_email_workspace'),
    )
    
    # Relationships
    workspace = relationship("WorkspaceModel", foreign_keys=[workspace_id],back_populates="invitations")
    role = relationship("Role", foreign_keys=[role_id], back_populates="invited_roles")
    invited_by = relationship("Users", foreign_keys=[invited_by_user_id], back_populates="sent_invitations")
    workspace_members = relationship("WorkspaceMembers", back_populates="invitation")

    # to_dict() inherited from SerializableMixin