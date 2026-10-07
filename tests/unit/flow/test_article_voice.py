"""The Brand Voice Profile steers the writing beside the persona (#161, option 1),
the humanize pass keeps that voice, and no prompt aims at AI detectors (#137)."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.api.database.async_database as database_module
import src.flow.engines.agent.middleware.persona_middleware as persona_module
import src.utils.loop_bridge as loop_module
from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
from src.flow.engines.content.generation.article_voice import (
    article_voice,
    fetch_brand_voice_profile,
    format_voice_for_rewrite,
    format_voice_for_writer,
)
from src.flow.engines.content.generation.humanize_content import _build_prompt_data
from src.flow.prompts.human.humanize import get_humanize_prompt
from src.flow.prompts.system.content import CONTENT_SYSTEM_PROMPT
from src.flow.prompts.system.humanize import HUMANIZE_SYSTEM_PROMPT

PROFILE = {
    "traits": ["Technical", "Informative", "Community-driven", "", 7],
    "customer_profile": "Developers and marketing teams at small software companies.",
}


def test_voice_keeps_the_traits_and_the_customer_profile():
    voice = article_voice("Calm, plain-spoken.", PROFILE)

    assert voice == {
        "persona_tone": "Calm, plain-spoken.",
        "brand_traits": ["Technical", "Informative", "Community-driven"],
        "customer_profile": "Developers and marketing teams at small software companies.",
        "brand_name": "",
        "about": "",
        "selling_position": "",
        "target_audience": [],
        "content_pillars": [],
    }


def test_voice_is_clipped():
    voice = article_voice("x" * 2000, {"traits": ["t" * 200] * 20, "customer_profile": "c" * 2000})

    assert len(voice["persona_tone"]) <= 600 and voice["persona_tone"].endswith("…")
    assert len(voice["brand_traits"]) == 8
    assert all(len(t) <= 60 for t in voice["brand_traits"])
    assert len(voice["customer_profile"]) <= 600


def test_writer_block_puts_the_persona_first():
    with_persona = format_voice_for_writer(article_voice("Calm.", PROFILE))
    without = format_voice_for_writer(article_voice(None, PROFILE))

    assert "Technical, Informative, Community-driven" in with_persona
    assert "Developers and marketing teams" in with_persona
    assert "your own Voice & Tone above comes first" in with_persona
    assert "this voice sets the tone" in without
    assert format_voice_for_writer(article_voice("Calm.", None)) == ""


def test_rewrite_instruction_carries_the_same_voice():
    text = format_voice_for_rewrite(article_voice("Calm.", PROFILE))

    assert "THE ARTICLE'S VOICE" in text and "outranks every general style rule" in text
    assert "The author's tone (comes first): Calm." in text
    assert "The brand's voice: Technical, Informative, Community-driven" in text
    assert "follow the author's" in text
    assert format_voice_for_rewrite(None) == ""
    assert format_voice_for_rewrite(article_voice(None, None)) == ""


# --- the fresh read --------------------------------------------------------------


async def test_profile_read_returns_traits_and_customer_profile(monkeypatch):
    @asynccontextmanager
    async def fake_db():
        yield SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(
                    first=lambda: (
                        ["Technical"],
                        "Developers.",
                        "Acme CMS",
                        "Acme CMS is a headless CMS.",
                        "Fast to set up.",
                        ["Developers"],
                        "not a list",
                    )
                )
            )
        )

    monkeypatch.setattr(database_module, "get_pooled_langgraph_db_context", fake_db)
    monkeypatch.setattr(loop_module, "run_on_main_loop", lambda coro: coro)

    profile = await fetch_brand_voice_profile("9eda8ec9-f71c-480a-8226-8d8361a31391")

    assert profile == {
        "traits": ["Technical"],
        "customer_profile": "Developers.",
        "brand_name": "Acme CMS",
        "about": "Acme CMS is a headless CMS.",
        "selling_position": "Fast to set up.",
        "target_audience": ["Developers"],
        "content_pillars": [],
    }


async def test_profile_read_never_raises(monkeypatch):
    def boom(_coro):
        _coro.close()
        raise RuntimeError("database down")

    monkeypatch.setattr(loop_module, "run_on_main_loop", boom)

    assert await fetch_brand_voice_profile("9eda8ec9-f71c-480a-8226-8d8361a31391") is None
    assert await fetch_brand_voice_profile(None) is None


# --- the writer ------------------------------------------------------------------


OUTLINE = {"title": "Headless CMS for small teams", "target_word_count": 1200}


def test_writer_prompt_carries_the_brand_voice():
    middleware = PersonaInjectionMiddleware(counters={})

    prompt = middleware._build_full_content_prompt(
        None, OUTLINE, 1200, "blog", voice=article_voice(None, PROFILE)
    )
    plain = middleware._build_full_content_prompt(None, OUTLINE, 1200, "blog")

    assert "THE BRAND'S VOICE" in prompt and "Community-driven" in prompt
    assert "THE BRAND'S VOICE" not in plain


async def test_the_agent_hook_reads_the_profile_and_records_the_voice(monkeypatch):
    counters = {}
    middleware = PersonaInjectionMiddleware(counters=counters)
    persona = SimpleNamespace(
        name="Mobeen",
        full_name="Mobeen Abdullah",
        professional_title="Founder",
        description=None,
        areas_of_expertise=None,
        pain_points=None,
        behaviors=None,
        bio=None,
        tone_of_voice="Calm, plain-spoken.",
        demographics=None,
        goals=None,
        linkedin_url=None,
    )
    monkeypatch.setattr(middleware, "_fetch_best_persona", AsyncMock(return_value=persona))
    monkeypatch.setattr(
        persona_module, "fetch_brand_voice_profile", AsyncMock(return_value=PROFILE)
    )
    monkeypatch.setattr(persona_module, "persona_profile_text", lambda _p: "profile")
    state = {
        "serp_payload": {"workspace_id": "w", "user_id": "u"},
        "content": {"outline": OUTLINE, "content_type": "blog"},
        "messages": [],
    }

    update = await middleware.abefore_agent(state, runtime=None)

    system = next(m for m in update["messages"] if m.__class__.__name__ == "SystemMessage")
    assert "Calm, plain-spoken." in system.content  # the persona's tone
    assert "Community-driven" in system.content  # the brand's voice
    assert system.content.index("Calm, plain-spoken.") < system.content.index("Community-driven")
    assert counters["article_voice"]["brand_traits"] == [
        "Technical",
        "Informative",
        "Community-driven",
    ]


# --- the humanize pass -------------------------------------------------------------


def test_humanize_prompt_keeps_the_voice():
    data = _build_prompt_data(
        content_payload={"title": "T", "introduction": "Intro.", "body_markdown": "## A\n\nText."},
        content_type="blog",
        article_voice=article_voice("Calm.", PROFILE),
    )

    messages = get_humanize_prompt().format_messages(**data)

    # At system priority, after the general style rules it outranks.
    system = messages[0].content
    assert "THE ARTICLE'S VOICE" in system and "Community-driven" in system
    assert system.index("Use contractions") < system.index("THE ARTICLE'S VOICE")
    assert "THE ARTICLE'S VOICE" not in messages[-1].content


def test_humanize_prompt_without_a_voice_has_no_voice_line():
    data = _build_prompt_data(
        content_payload={"title": "T", "introduction": "Intro.", "body_markdown": "## A\n\nText."}
    )

    assert data["voice_instruction"] == ""
    messages = get_humanize_prompt().format_messages(**data)  # still formats
    assert "THE ARTICLE'S VOICE" not in messages[0].content


# --- no prompt aims at AI detectors (#137) --------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        HUMANIZE_SYSTEM_PROMPT,
        CONTENT_SYSTEM_PROMPT,
        PersonaInjectionMiddleware.CONTENT_INSTRUCTIONS,
        PersonaInjectionMiddleware.CONTENT_SYSTEM_PROMPT_TEMPLATE,
    ],
)
def test_no_prompt_names_a_detector(prompt):
    lowered = prompt.lower()
    for word in ("gptzero", "zerogpt", "detector", "perplexity", "burstiness", "ai-detectable"):
        assert word not in lowered


def test_the_rhythm_rules_stay():
    assert "Yoast flags 3 consecutive sentences sharing a starting word" in HUMANIZE_SYSTEM_PROMPT
    assert "uneven, occasionally surprising structure" in HUMANIZE_SYSTEM_PROMPT


def test_the_style_defaults_defer_to_the_voice():
    assert "unless the article's voice at the end of this prompt" in HUMANIZE_SYSTEM_PROMPT
    assert HUMANIZE_SYSTEM_PROMPT.count("unless the article's voice") == 2


# --- what the company knows and offers (FB2.21, rext-control#702) ------------------

FULL_PROFILE = {
    **PROFILE,
    "brand_name": "Acme CMS",
    "about": "Acme CMS is a headless CMS for small software teams. acme cms ships with previews.",
    "selling_position": "The quickest way to move a marketing site off a monolith.",
    "target_audience": ["Developers", "Marketing leads", ""],
    "content_pillars": ["Headless CMS", "Content operations"],
}


def test_the_writer_gets_what_the_company_knows_and_offers():
    from src.flow.engines.content.generation.article_voice import format_expertise_for_writer

    block = format_expertise_for_writer(article_voice(None, FULL_PROFILE))

    assert block.startswith("## WHAT THE COMPANY BEHIND THIS SITE KNOWS AND OFFERS")
    assert "**What it offers:** The quickest way to move a marketing site off a monolith." in block
    assert "**What it writes about:** Headless CMS; Content operations" in block
    assert "**Who it serves:** Developers; Marketing leads" in block
    assert "write as a practitioner at this company would" in block


def test_the_companys_own_name_is_not_put_in_front_of_the_writer():
    from src.flow.engines.content.generation.article_voice import format_expertise_for_writer

    block = format_expertise_for_writer(article_voice(None, FULL_PROFILE))

    assert "Acme CMS" not in block and "acme cms" not in block
    assert (
        "**What it does:** The company is a headless CMS for small software teams. the company ships"
        in block
    )
    # Knowing the company is never permission to name it: the mention has its own rules.
    assert "permission to name the company or its product" in block
    # A title or keyphrase that is the brand's own name must still carry it.
    assert "name it only where the article's own title or focus keyphrase already does" in block


def test_a_long_name_and_the_lists_are_cleared_of_it_too():
    from src.flow.engines.content.generation.article_voice import format_expertise_for_writer

    long_name = "Acme Content Management Systems and Publishing Tools for Small Software Teams Ltd"
    assert len(long_name) > 80
    profile = {
        "brand_name": long_name,
        "about": f"{long_name} builds a headless CMS.",
        "target_audience": [f"{long_name} customers", "Developers"],
        "content_pillars": [f"{long_name} tutorials", "Content operations"],
    }

    block = format_expertise_for_writer(article_voice(None, profile))

    assert "Acme Content Management" not in block
    assert "**What it does:** The company builds a headless CMS." in block
    assert "**What it writes about:** The company tutorials; Content operations" in block
    assert "**Who it serves:** The company customers; Developers" in block


def test_the_companys_own_statements_are_claim_evidence_without_a_mention():
    from src.flow.engines.content.generation.claim_integrity import build_claim_evidence

    voice = article_voice(
        None, {**FULL_PROFILE, "about": "Acme CMS has served 500 stores since 2018."}
    )

    evidence = build_claim_evidence(
        outline={}, brand_context=None, generation_meta={"article_voice": voice}
    )

    # No mention was approved, so no brand is named as the subject; its statements still count.
    assert evidence["brand_name"] == ""
    assert evidence["brand_documents"] == [
        "The company has served 500 stores since 2018.",
        "The quickest way to move a marketing site off a monolith.",
    ]
    # With a mention approved the same text isn't listed twice.
    promoted = build_claim_evidence(
        outline={},
        brand_context={"brand_name": "Acme CMS", "about": voice["about"], "selling_position": ""},
        generation_meta={"article_voice": voice},
    )
    assert promoted["brand_documents"].count(voice["about"]) == 1


def test_the_writers_block_carries_the_voice_then_the_expertise():
    block = format_voice_for_writer(article_voice("Calm.", FULL_PROFILE))

    voice_at = block.index("## THE BRAND'S VOICE")
    expertise_at = block.index("## WHAT THE COMPANY BEHIND THIS SITE KNOWS AND OFFERS")
    assert voice_at < expertise_at
    # A profile with only the offer still reaches the writer; one with nothing adds nothing.
    only_offer = format_voice_for_writer(article_voice(None, {"selling_position": "Fast."}))
    assert only_offer.startswith("## WHAT THE COMPANY BEHIND THIS SITE KNOWS AND OFFERS")
    assert format_voice_for_writer(article_voice(None, {})) == ""


def test_the_rewrite_is_not_given_the_offer():
    assert "monolith" not in format_voice_for_rewrite(article_voice("Calm.", FULL_PROFILE))
