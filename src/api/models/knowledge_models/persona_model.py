from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin


class Persona(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin):
    """Persona model - Stores extracted user personas for workspaces...."""
    __tablename__ = "persona"

    # id, workspace_id, created_at, updated_at provided by mixins
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

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="personas")

    # to_dict() inherited from SerializableMixin
