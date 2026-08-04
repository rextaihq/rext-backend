from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin


class Audience(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin):
    """Reader/buyer persona segment — split out of the old Persona table.

    Distinct from AuthorPersona: this describes WHO content is written for
    (demographics, psychographics, pain points), not who wrote it. A
    workspace can have multiple named audience segments.
    """
    __tablename__ = "audience"

    # id, workspace_id, created_at, updated_at provided by mixins
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    demographics = Column(JSONB, nullable=True)  # {age_range, job_titles: [...], seniority, company_size, location}
    psychographics = Column(JSONB, nullable=True)  # {fears: [...], decision_levers: [...], values: [...]}
    pain_points = Column(JSONB, nullable=True)  # List[str]
    goals = Column(JSONB, nullable=True)  # List[str]
    behaviors = Column(JSONB, nullable=True)  # List[str]
    objections = Column(JSONB, nullable=True)  # List[str]
    preferred_channels = Column(JSONB, nullable=True)  # List[str]
    buying_stage = Column(String(50), nullable=True)  # awareness | consideration | decision | retention

    workspace = relationship("WorkspaceModel", back_populates="audiences")

    def to_dict(self, **kwargs) -> dict:
        data = super().to_dict(**kwargs)
        list_fields = ["pain_points", "goals", "behaviors", "objections", "preferred_channels"]
        for field in list_fields:
            if data.get(field) is None:
                data[field] = []
        if data.get("demographics") is None:
            data["demographics"] = {}
        if data.get("psychographics") is None:
            data["psychographics"] = {}
        return data
