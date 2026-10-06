"""The writer speaks from the persona's experience only when it fits the subject (G56, #501).

E7's proof run wrote a software founder's bio ("I'm Mobeen Abdullah, Founder & Lead Developer at
Nextly…") into a bakery article as "My Experience With Structured Content". A persona whose
expertise doesn't fit the article lends its voice, and no bio, name or background.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

import src.flow.engines.agent.middleware.persona_middleware as persona_module
from src.flow.engines.agent.middleware.persona_middleware import (
    PersonaInjectionMiddleware,
    persona_fits_outline,
)

pytestmark = pytest.mark.unit

FOUNDER = SimpleNamespace(
    id="founder-1",
    name="Mobeen",
    full_name="Mobeen Abdullah",
    professional_title="Founder & Lead Developer at Nextly",
    description="Builds Nextly, an open-source headless CMS.",
    areas_of_expertise=["Open-source software", "Next.js", "Content management"],
    pain_points="Content models that drift between teams.",
    behaviors=None,
    bio="I focus on open-source software, Next.js and content management, especially structured schemas.",
    tone_of_voice="Calm, plain-spoken.",
    demographics=None,
    goals=None,
    linkedin_url="https://www.linkedin.com/in/example",
)

BAKERY_OUTLINE = {
    "title": "Email Marketing Ideas for Local Bakeries",
    "focus_keyphrase": "email marketing ideas for local bakeries",
    "target_word_count": 1200,
}
CMS_OUTLINE = {
    "title": "The Best CMS for Next.js",
    "focus_keyphrase": "next.js cms",
    "target_word_count": 1200,
}


def _prompt(outline, fits_topic):
    middleware = PersonaInjectionMiddleware(counters={})
    return middleware._build_full_content_prompt(
        FOUNDER, outline, 1200, "blog", fits_topic=fits_topic
    )


def test_a_fitting_persona_keeps_its_bio_and_identity():
    prompt = _prompt(CMS_OUTLINE, True)

    assert "AUTHOR BIO — PLACEMENT & STRUCTURE" in prompt
    assert "omitting it is an automatic failure" in prompt
    assert "YOUR AUTHOR IDENTITY — EMBODY THIS FULLY" in prompt
    assert FOUNDER.bio in prompt
    assert "Use your name **Mobeen Abdullah**" in prompt
    assert "THE AUTHOR'S FULL NAME MUST APPEAR IN THE ARTICLE" in prompt
    assert "Within the first 200 words, establish the author's background" in prompt
    assert FOUNDER.linkedin_url in prompt
    assert "AUTHOR BIO — NONE IN THIS ARTICLE" not in prompt


def test_an_off_topic_persona_gives_its_voice_and_no_bio():
    prompt = _prompt(BAKERY_OUTLINE, False)

    assert "AUTHOR BIO — NONE IN THIS ARTICLE" in prompt
    assert "AUTHOR BIO — PLACEMENT & STRUCTURE" not in prompt
    assert "omitting it is an automatic failure" not in prompt
    assert "This Subject Is Outside Your Expertise" in prompt
    # The background and the lived pain points are what an experience section is built from.
    assert FOUNDER.bio not in prompt
    assert FOUNDER.pain_points not in prompt
    assert "Use your name" not in prompt
    # Every identity directive goes with the bio (Codex on #837): the name, the background in the
    # first 200 words, the expertise in every section, the link. The name isn't in the prompt at
    # all, so the article can't repeat it.
    assert "FULL NAME MUST APPEAR" not in prompt
    assert "Within the first 200 words, establish the author's background" not in prompt
    assert "Weave the persona's expertise" not in prompt
    assert FOUNDER.full_name not in prompt
    assert FOUNDER.linkedin_url not in prompt
    assert "Founder & Lead Developer at Nextly" not in prompt
    # The voice stays.
    assert "Calm, plain-spoken." in prompt


def test_the_outline_steps_own_score_decides():
    fitting = {
        **BAKERY_OUTLINE,
        "persona_recommendations": [
            {"persona_id": "founder-1", "breakdown": {"topic": 60.0, "title": 0.0}}
        ],
    }
    off_topic = {
        **CMS_OUTLINE,
        "persona_recommendations": [
            {"persona_id": "founder-1", "breakdown": {"topic": 0.0, "title": 10.0}}
        ],
    }

    assert persona_fits_outline(FOUNDER, fitting) is True
    assert persona_fits_outline(FOUNDER, off_topic) is False


def test_without_a_recorded_score_the_fit_is_taken_from_the_outline():
    assert persona_fits_outline(FOUNDER, BAKERY_OUTLINE) is False
    assert persona_fits_outline(FOUNDER, CMS_OUTLINE) is True


@pytest.mark.parametrize(("outline", "fits"), [(BAKERY_OUTLINE, False), (CMS_OUTLINE, True)])
async def test_the_agent_hook_follows_the_fit(monkeypatch, outline, fits):
    counters = {}
    middleware = PersonaInjectionMiddleware(counters=counters)
    monkeypatch.setattr(middleware, "_fetch_best_persona", AsyncMock(return_value=FOUNDER))
    monkeypatch.setattr(persona_module, "fetch_brand_voice_profile", AsyncMock(return_value={}))
    monkeypatch.setattr(persona_module, "persona_profile_text", lambda _p: "profile")
    state = {
        "serp_payload": {"workspace_id": "w", "user_id": "u"},
        "content": {"outline": outline, "content_type": "blog"},
        "messages": [HumanMessage(content="Write it.", id="h1")],
    }

    update = await middleware.abefore_agent(state, runtime=None)

    human = next(m for m in update["messages"] if m.__class__.__name__ == "HumanMessage")
    system = next(m for m in update["messages"] if m.__class__.__name__ == "SystemMessage")
    if fits:
        assert "Place an author bio section in the MIDDLE" in human.content
        assert "Connect with Mobeen Abdullah on LinkedIn" in human.content
        assert counters["author_profile"] == "profile"
        assert "AUTHOR BIO — PLACEMENT & STRUCTURE" in system.content
    else:
        assert "THIS SUBJECT IS OUTSIDE THE AUTHOR'S EXPERTISE" in human.content
        assert "author bio section in the MIDDLE" not in human.content
        assert "LinkedIn" not in human.content.replace("no LinkedIn line", "")
        assert FOUNDER.full_name not in human.content
        assert FOUNDER.full_name not in system.content
        # No profile, so an experience claim slipped in is unsupported in validation.
        assert counters["author_profile"] == ""
        assert "AUTHOR BIO — NONE IN THIS ARTICLE" in system.content
