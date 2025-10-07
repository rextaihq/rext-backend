"""Unit tests for TopicEnrichmentService."""

from src.services.topic_enrichment_service import TopicEnrichmentService
from src.states.schemas import (
    BasicTopicScore,
    TopicGeneration,
    TopicScore,
)


def _build_basic_topic(**overrides):
    """Helper to create a minimal basic topic payload for enrichment."""
    base = {
        "title": "Top 10 AI Trends",
        "angle": "Practical AI implementations for SMBs",
        "description": "Explores actionable AI trends small businesses can adopt",
        "channel_fit": ["blog", "social-media"],
        "audience_fit": ["small-business", "tech-savvy"],
        "why_it_works": "Combines trend analysis with actionable insights",
        "tags": ["AI", "Trends", "SMB"],
        "scores": {
            "relevance": 0.9,
            "seo_potential": 0.85,
            "trend_level": 0.8,
            "uniqueness": 0.75,
            "reader_interest": 0.88,
            "actionable_potential": 0.92,
            "brand_alignment": 0.9,
            "controversy": 0.1,
        },
    }
    base.update(overrides)
    return base


def test_enrich_topic_returns_topic_generation_model():
    """enrich_topic should build a TopicGeneration object with rich metadata."""
    service = TopicEnrichmentService()
    basic_topic = _build_basic_topic()
    input_params = {"industry": "Technology"}

    result = service.enrich_topic(basic_topic, input_params)

    assert isinstance(result, TopicGeneration)
    assert result.title == basic_topic["title"]
    assert result.suggested_defaults.platform == "Website"
    assert "ai" in result.suggested_defaults.primaryKeywords[0].lower()


def test_enrich_topic_handles_basic_topic_score_model_instance():
    """Service should support BasicTopicScore pydantic instance input."""
    service = TopicEnrichmentService()
    basic_topic = _build_basic_topic(
        scores=BasicTopicScore(
            relevance=0.95,
            seo_potential=0.8,
            trend_level=0.7,
            uniqueness=0.85,
            reader_interest=0.9,
            actionable_potential=0.88,
            brand_alignment=0.9,
            controversy=0.15,
        )
    )
    input_params = {"industry": "Finance"}

    enriched = service.enrich_topic(basic_topic, input_params)

    assert isinstance(enriched.scores, TopicScore)
    assert enriched.scores.relevance == 0.95
    assert "Finance" == enriched.suggested_defaults.industry


def test_enrich_topic_generates_goal_alignment_based_on_content():
    """Goal alignment should include Drive SEO for tutorial-like content."""
    service = TopicEnrichmentService()
    basic_topic = _build_basic_topic(
        title="How to Implement Zero-Trust Security",
        angle="Step-by-step implementation guide",
        channel_fit=["blog"],
    )
    input_params = {"industry": "Cybersecurity"}

    enriched = service.enrich_topic(basic_topic, input_params)

    assert "Drive SEO" in enriched.goal_alignment.primary_goals
    assert enriched.content_guidance.recommended_structure in {"tutorial", "guide"}
