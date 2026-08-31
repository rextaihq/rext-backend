from sqlalchemy import CheckConstraint, Column, String, Text
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
    # Where a persona's picture comes from, and what it is derived from.
    #
    # avatar_url holds one URL whatever its origin - uploaded, pasted, scraped
    # from the site, or built from an address - so a reader never has to know
    # which to look in. avatar_source records which it was, because a
    # photograph of the person and a generated placeholder are not the same
    # claim and the interface would otherwise present them identically.
    #
    # email exists so a Gravatar can be derived for someone the crawl found no
    # picture of. It is the person's own address as the site publishes it or a
    # user enters it, never a shared inbox.
    avatar_url = Column(String(500), nullable=True)
    # Constrained rather than free text: four values are meaningful and
    # anything else is a bug that would read as a fifth kind of picture. The
    # check lives in the database so a route that forgets to validate cannot
    # write one.
    avatar_source = Column(
        String(20),
        CheckConstraint(
            "avatar_source IS NULL OR avatar_source IN "
            "('custom', 'page', 'gravatar', 'generated')",
            name="ck_persona_avatar_source"),
        nullable=True)
    email = Column(String(320), nullable=True)
    custom_metadata = Column(JSONB, nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="personas")

    @property
    def is_recommended(self) -> bool:
        """Whether this is the persona the brand should write as.

        Derived from custom_metadata rather than stored in a column of its own.
        The recommendation is recomputed from scratch on every extraction - it
        follows from the scores, and a score that moves should move it - so a
        column would be a second place for the same fact to live and a chance
        for the two to disagree.
        """
        return bool((self.custom_metadata or {}).get("is_recommended"))

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
