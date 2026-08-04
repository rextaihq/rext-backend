from sqlalchemy import Column, String, Text, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin


class AuthorPersona(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin):
    """Author/expert identity used for E-E-A-T bylines — WHO wrote the content.

    Narrowed from the old ``Persona`` table: buyer/reader fields
    (demographics, pain_points, goals, behaviors) moved to ``Audience``,
    since those describe who content is FOR, not who wrote it.
    """
    __tablename__ = "author_persona"

    # id, workspace_id, created_at, updated_at provided by mixins
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # E-E-A-T professional identity fields (schema.org/Person-aligned)
    full_name = Column(String(255), nullable=True)
    professional_title = Column(String(255), nullable=True)
    areas_of_expertise = Column(JSONB, nullable=True)  # List[str]
    experience_type = Column(String(50), nullable=True)  # everyday_experience | formal_expertise | both
    years_of_experience = Column(Integer, nullable=True)
    credentials = Column(JSONB, nullable=True)  # List[{credential, issuer, year}]
    employer = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    social_profiles = Column(JSONB, nullable=True)  # List[{platform, url}] — generalizes linkedin_url
    writing_voice = Column(String(255), nullable=True)  # renamed from tone_of_voice
    avatar_url = Column(String(500), nullable=True)
    custom_metadata = Column(JSONB, nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="author_personas")
    evidence = relationship("ExtractionEvidence", back_populates="author_persona", cascade="all, delete-orphan", passive_deletes=True)

    def to_dict(self, **kwargs) -> dict:
        """Custom serialization ensuring list fields are always lists.

        Also surfaces the legacy-named backward-compat properties below
        (linkedin_url, tone_of_voice, pain_points, behaviors, demographics,
        goals) since to_dict() otherwise only reflects real Column objects,
        not Python @property descriptors — without this, API responses
        would silently omit them even though the properties exist.
        """
        data = super().to_dict(**kwargs)
        list_fields = ["areas_of_expertise", "credentials", "social_profiles"]
        for field in list_fields:
            if data.get(field) is None:
                data[field] = []
        data["linkedin_url"] = self.linkedin_url
        data["tone_of_voice"] = self.tone_of_voice
        data["pain_points"] = self.pain_points
        data["behaviors"] = self.behaviors
        data["demographics"] = self.demographics
        data["goals"] = self.goals
        return data

    @property
    def linkedin_url(self) -> str | None:
        """Backward-compatible accessor for the primary LinkedIn profile."""
        for profile in (self.social_profiles or []):
            if isinstance(profile, dict) and profile.get("platform") == "linkedin":
                return profile.get("url")
        return None

    @property
    def tone_of_voice(self) -> str | None:
        """Backward-compatible alias for the legacy tone_of_voice field."""
        return self.writing_voice

    @property
    def pain_points(self) -> list[str]:
        """Legacy compatibility property for older persona consumers."""
        return []

    @property
    def behaviors(self) -> list[str]:
        """Legacy compatibility property for older persona consumers."""
        return []

    @property
    def demographics(self) -> dict:
        """Legacy compatibility property for older persona consumers."""
        return {}

    @property
    def goals(self) -> list[str]:
        """Legacy compatibility property for older persona consumers."""
        return []


Persona = AuthorPersona
