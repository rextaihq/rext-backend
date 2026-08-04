from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin


class ExtractionEvidence(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin):
    """Confidence/source/citation for one extracted field.

    Generic table keyed by entity rather than sibling confidence/source
    columns on every table — exactly one of brand_id / brand_voice_id /
    author_persona_id is set per row. Captures the signal the extraction
    LLM already computes (e.g. PersonaExtract.source) that was previously
    discarded before persistence.
    """
    __tablename__ = "extraction_evidence"

    brand_id = Column(UUID(as_uuid=True), ForeignKey("brand.id", ondelete="CASCADE"), nullable=True, index=True)
    brand_voice_id = Column(UUID(as_uuid=True), ForeignKey("brand_voice.id", ondelete="CASCADE"), nullable=True, index=True)
    author_persona_id = Column(UUID(as_uuid=True), ForeignKey("author_persona.id", ondelete="CASCADE"), nullable=True, index=True)

    field_name = Column(String(100), nullable=False)
    extracted_value = Column(Text, nullable=True)  # snapshot for audit even if field later edited
    confidence = Column(Float, nullable=True)  # 0.0 - 1.0
    source_url = Column(String(500), nullable=True)
    supporting_excerpt = Column(Text, nullable=True)
    extraction_method = Column(String(50), nullable=False, default="llm_structured_output")
    # llm_structured_output | heuristic | manual_entry | user_edited

    __table_args__ = (
        CheckConstraint(
            "(num_nonnulls(brand_id, brand_voice_id, author_persona_id) = 1)",
            name="ck_extraction_evidence_exactly_one_entity",
        ),
        Index("ix_extraction_evidence_workspace_field", "workspace_id", "field_name"),
    )

    workspace = relationship("WorkspaceModel", back_populates="extraction_evidence")
    brand = relationship("Brand", back_populates="evidence")
    brand_voice = relationship("BrandVoice", back_populates="evidence")
    author_persona = relationship("AuthorPersona", back_populates="evidence")
