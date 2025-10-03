from sqlalchemy import Column, String,func,DateTime,Boolean
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
import uuid

class TopicsModel(Base):
    __tablename__ = "topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)  # Changed to String to match schema
    title = Column(String, nullable=False)
    angle = Column(String, nullable=False)
    description = Column(String, nullable=False)  # New field
    channel_fit = Column(ARRAY(String), nullable=False)
    audience_fit = Column(ARRAY(String), nullable=False)
    why_it_works = Column(String, nullable=True)
    scores = Column(JSONB, nullable=False)
    tags = Column(ARRAY(String), nullable=True)
    suggested_defaults = Column(JSONB, nullable=False)  # New field
    goal_alignment = Column(JSONB, nullable=False)  # New field
    content_guidance = Column(JSONB, nullable=False)  # New field
    audience_insights = Column(JSONB, nullable=False)  # New field
    internal_research_config = Column(JSONB, nullable=False)  # New field
    approved = Column(Boolean, nullable=True, server_default="false")
    approved_at = Column(DateTime(timezone=True), nullable=True)  # When topic was approved
    user_settings = Column(JSONB, nullable=False)  # New field
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # Generated date
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),nullable=True)

    # Content relationship
    content_items = relationship("Content", back_populates="topic")

    def to_dict(self) -> dict:
        """Custom serialization for Topics model"""
        base_dict = super().to_dict()

        # Add computed fields and enhanced metadata
        scores = self.scores or {}
        base_dict.update({
            'topic_metadata': {
                'title': self.title,
                'angle': self.angle,
                'description': self.description,
                'channel_compatibility': self.channel_fit or [],
                'target_audience': self.audience_fit or [],
                'reasoning': self.why_it_works
            },
            'performance_metrics': {
                'overall_score': self._calculate_overall_score(scores),
                'detailed_scores': scores,
                'tags': self.tags or []
            },
            'configuration': {
                'suggested_defaults': self.suggested_defaults or {},
                'goal_alignment': self.goal_alignment or {},
                'content_guidance': self.content_guidance or {},
                'audience_insights': self.audience_insights or {},
                'research_config': self.internal_research_config or {},
                'user_settings': self.user_settings or {}
            }
        })

        return base_dict

    def _calculate_overall_score(self, scores: dict) -> float:
        """Calculate overall score from individual metrics"""
        if not scores:
            return 0.0

        score_values = []
        for key, value in scores.items():
            if isinstance(value, (int, float)) and key != 'controversy':
                score_values.append(value)
            elif key == 'controversy' and isinstance(value, (int, float)):
                # Invert controversy score (lower is better)
                score_values.append(10 - value)

        return round(sum(score_values) / len(score_values), 2) if score_values else 0.0