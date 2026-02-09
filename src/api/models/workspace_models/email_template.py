import uuid
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
import enum


class TemplateType(str, enum.Enum):
    """Email template types"""
    WORKSPACE_INVITATION = "workspace_invitation"
    INVITATION_ACCEPTED = "invitation_accepted"
    ROLE_CHANGED = "role_changed"
    MEMBER_REMOVED = "member_removed"
    WELCOME = "welcome"


class EmailTemplate(Base, SerializableMixin):
    """
    Email templates for workspace notifications.

    Allows workspace owners to customize email content sent to members.
    Supports template variables for dynamic content.
    """
    __tablename__ = "email_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=True)
    template_type = Column(SQLEnum(TemplateType), nullable=False)

    # Template content
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)

    # Metadata
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # System default templates
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    workspace = relationship("WorkspaceModel", foreign_keys=[workspace_id], back_populates="email_templates")
    created_by = relationship("Users", foreign_keys=[created_by_user_id])

    def to_dict(self, **kwargs):
        """Custom serialization handling enum values"""
        data = super().to_dict(**kwargs)
        # Handle enum serialization
        if isinstance(self.template_type, TemplateType):
            data['template_type'] = self.template_type.value
        return data
