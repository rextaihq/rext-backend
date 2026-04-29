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
    areas_of_expertise = Column(JSONB , nullable=True)
    tone_of_voice = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    
    # User persona fields
    demographics = Column(Text, nullable=True)
    pain_points = Column(Text, nullable=True)
    goals = Column(Text, nullable=True)
    behaviors = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
    custom_metadata = Column(JSONB, nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="personas")

    def to_dict(self, **kwargs) -> dict:
        """Custom serialization handling list fields stored as text"""
        data = super().to_dict(**kwargs)
        
        # Split text fields into lists for frontend compatibility
        text_list_fields = ['areas_of_expertise', 'pain_points', 'goals', 'behaviors']
        for field in text_list_fields:
            if field in data and isinstance(data[field], str):
                # Filter out empty strings if the field is empty or whitespace
                items = [item.strip() for item in data[field].split(',') if item.strip()]
                data[field] = items
            elif field not in data or data[field] is None:
                data[field] = []
                
        return data
