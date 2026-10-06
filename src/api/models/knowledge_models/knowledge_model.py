import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


# Brand Voice
class BrandVoice(Base, SerializableMixin):
    __tablename__ = "brand_voice"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    brand_name = Column(String(255), nullable=True)
    about = Column(Text, nullable=True)
    customer_profile = Column(Text, nullable=True)
    selling_position = Column(Text, nullable=True)
    target_audience = Column(JSONB, nullable=True)
    brand_voice = Column(JSONB, nullable=True)
    competitors = Column(JSONB, nullable=True)
    content_pillar = Column(JSONB, nullable=True)
    # for storing compliance metadata
    site_compliance = Column(JSONB, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True
    )

    workspace = relationship("WorkspaceModel", back_populates="brand_voices")

    def to_dict(self, **kwargs) -> dict:
        """Custom serialization handling list fields"""
        data = super().to_dict(**kwargs)
        # Ensure list fields are always lists (even if stored as empty JSONB)
        list_fields = [
            "target_audience",
            "brand_voice",
            "competitors",
            "content_strategy",
            "secondary_pillars",
        ]
        for field in list_fields:
            if field in data:
                if data[field] is None:
                    data[field] = []
            else:
                data[field] = []
        return data
