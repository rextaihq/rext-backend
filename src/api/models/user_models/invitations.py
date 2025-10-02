import uuid
from sqlalchemy import Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from datetime import datetime
from src.api.database.database import Base

class UserInvitations(Base):
    __tablename__ = "user_invitations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    email = Column(String(255), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    invitation_token = Column(String(255), unique=True, nullable=False)
    status = Column(String(50), default="pending")  # e.g., pending, accepted, revoked
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)

    # add a constraint to ensure that the combination of email and workspace_id is unique
    __table_args__ = (
        UniqueConstraint('email', 'workspace_id', name='uq_email_workspace'),
    )
    
    # Relationships
    workspace = relationship("WorkspaceModel", foreign_keys=[workspace_id],back_populates="invitations")
    role = relationship("Role", foreign_keys=[role_id], back_populates="invited_roles")
    invited_by = relationship("Users", foreign_keys=[invited_by_user_id], back_populates="sent_invitations")
    workspace_members = relationship("WorkspaceMembers", back_populates="invitation")

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "role_id": str(self.role_id),
            "invited_by_user_id": str(self.invited_by_user_id),
            "invitation_token": self.invitation_token,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }