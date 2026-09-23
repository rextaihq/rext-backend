"""Persona relevance is scored against the article, not the workspace."""

import pytest

from src.flow.engines.content.generation.persona_relevance import rank_personas, score_persona


class _Persona:
    """Stand-in for the Persona row the outline node loads."""

    def __init__(
        self, persona_id, name, professional_title=None, areas_of_expertise=None, bio=None
    ):
        self.id = persona_id
        self.name = name
        self.full_name = name
        self.professional_title = professional_title
        self.areas_of_expertise = areas_of_expertise or []
        self.bio = bio
        self.description = None


SEO_PERSONA = _Persona(
    "seo-1",
    "Sara Ortiz",
    professional_title="SEO Strategist",
    areas_of_expertise=["SEO", "Keyword Research", "Technical SEO"],
)
AI_PERSONA = _Persona(
    "ai-1",
    "Amir Khan",
    professional_title="AI Researcher",
    areas_of_expertise=["Machine Learning", "LLM Evaluation"],
)
WEB_PERSONA = _Persona(
    "web-1",
    "Wren Bello",
    professional_title="Web Designer",
    areas_of_expertise=["Web Design", "Accessibility"],
)

ALL_PERSONAS = [SEO_PERSONA, AI_PERSONA, WEB_PERSONA]


@pytest.mark.unit
def test_seo_persona_is_recommended_for_an_seo_article():
    ranked = rank_personas(
        ALL_PERSONAS,
        topic="Technical SEO audits for large ecommerce sites",
        title="How to run a technical SEO audit",
        search_intent="informational",
        content_type="how_to",
    )

    assert ranked[0].persona_id == "seo-1"
    assert ranked[0].score > ranked[1].score


@pytest.mark.unit
def test_ai_persona_is_recommended_for_an_ai_article():
    ranked = rank_personas(
        ALL_PERSONAS,
        topic="Evaluating LLM output quality",
        title="A practical guide to LLM evaluation",
        search_intent="informational",
        content_type="blog",
    )

    assert ranked[0].persona_id == "ai-1"


@pytest.mark.unit
def test_every_dimension_is_scored_and_reported():
    relevance = score_persona(
        SEO_PERSONA,
        topic="Keyword research for SaaS",
        title="Keyword research that actually converts",
        search_intent="commercial",
        content_type="buying_guide",
    )

    assert set(relevance.breakdown) == {"topic", "title", "search_intent", "content_type"}
    assert relevance.breakdown["topic"] > 0
    assert 0 <= relevance.score <= 100
    assert relevance.to_dict()["persona_id"] == "seo-1"


@pytest.mark.unit
def test_search_intent_and_content_type_change_the_ranking():
    """The same personas, ranked differently by intent and content type alone."""
    reviewer = _Persona(
        "rev-1",
        "Rae Lund",
        professional_title="Product Reviewer",
        areas_of_expertise=["Product Reviews", "Buying Advice"],
    )
    teacher = _Persona(
        "edu-1",
        "Ted Mensah",
        professional_title="Educator",
        areas_of_expertise=["Tutorials", "Training"],
    )

    commercial = rank_personas(
        [teacher, reviewer],
        topic="Standing desks",
        title="Standing desks",
        search_intent="commercial",
        content_type="buying_guide",
    )
    informational = rank_personas(
        [reviewer, teacher],
        topic="Standing desks",
        title="Standing desks",
        search_intent="informational",
        content_type="how_to",
    )

    assert commercial[0].persona_id == "rev-1"
    assert informational[0].persona_id == "edu-1"


@pytest.mark.unit
def test_a_persons_name_never_scores_as_expertise():
    """ "Mark Webb" must not be the recommended author for an article on the web."""
    namesake = _Persona("name-1", "Mark Webb", professional_title="Accountant")

    ranked = rank_personas(
        [namesake, WEB_PERSONA],
        topic="Web design systems",
        title="Building a web design system",
        search_intent="informational",
        content_type="blog",
    )

    assert ranked[0].persona_id == "web-1"


@pytest.mark.unit
def test_scoring_is_deterministic():
    first = rank_personas(
        ALL_PERSONAS, topic="SEO", title="SEO", search_intent="informational", content_type="blog"
    )
    second = rank_personas(
        ALL_PERSONAS, topic="SEO", title="SEO", search_intent="informational", content_type="blog"
    )

    assert [(r.persona_id, r.score) for r in first] == [(r.persona_id, r.score) for r in second]
