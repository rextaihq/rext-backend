from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
import uuid
from datetime import datetime, timezone


class Persona(Base, SerializableMixin):
    """Persona model — stores extracted user personas for workspaces.

    Each persona belongs to a workspace and captures either an expert persona
    (with E-E-A-T professional fields) or a user/audience persona (with
    demographics, pain points, goals, and behaviors).  Personas are used
    during content generation to tailor tone, style, and subject-matter depth.
    """
    __tablename__ = "persona"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # E-E-A-T professional fields for expert personas
    full_name = Column(String(255), nullable=True)
    professional_title = Column(String(255), nullable=True)
    areas_of_expertise = Column(Text, nullable=True) 
    tone_of_voice = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    
    # User persona fields
    demographics = Column(Text, nullable=True)
    pain_points = Column(Text, nullable=True)
    goals = Column(Text, nullable=True)
    behaviors = Column(Text, nullable=True)
    custom_metadata = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="personas")

    def to_dict(self, **kwargs):
        """Serialize persona using mixin."""
        return super().to_dict(**kwargs)
