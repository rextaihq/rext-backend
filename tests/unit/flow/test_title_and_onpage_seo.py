"""Regression tests for title generation and content-level on-page SEO.

Each test pins one production defect, written against what a reader of the
finished article (or the SEO panel) would notice:

1. Focus keyphrase missing from a generated title.
2. Title outside the 50-59 character range reaching the topic picker.
3. The user-selected title being changed by a later stage.
4. A title about one subject (agencies) with a body about another (tools).
5. Focus keyphrase missing from the meta description.
6. Focus keyphrase missing from the introduction.
7. Meta description missing entirely.
8. A JSON-LD finding shown in the content-level SEO issues list.
9. JSON-LD score compensation pushing the score above 100.
"""

from __future__ import annotations

from enum import Enum
from unittest.mock import AsyncMock, patch

import pytest

from src.flow.engines.content.generation import topic_generation as tg
from src.flow.engines.content.generation.onpage_seo import (
    enforce_onpage_seo,
    merge_preserving_existing,
)
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.seo_title_rules import (
    TITLE_MAX_CHARS,
    TITLE_MIN_CHARS,
    contains_keyphrase,
    repair_title,
    title_is_valid,
    title_violations,
)
from src.flow.engines.content.generation.title_subject import find_subject_mismatch
from src.flow.engines.content.generation.validation import (
    check_focus_keyphrase_in_introduction,
    check_focus_keyphrase_in_meta_description,
    check_focus_keyphrase_in_title,
    check_meta_description_present,
    check_selected_title_preserved,
    check_title_subject_alignment,
)
from src.flow.engines.content.utils import utils as seokar_utils
from src.flow.model.structure.topics import SEOTopic, SEOTopics

KEYPHRASE = "seo agencies"
# 57 characters, contains the keyphrase.
VALID_TITLE = "Best SEO Agencies for Small Businesses: How to Choose One"


def _spec(**overrides) -> dict:
    outline = {"title": VALID_TITLE, "focus_keyphrase": KEYPHRASE}
    spec = build_requirements_spec(outline, "comparison", KEYPHRASE, VALID_TITLE)
    spec.update(overrides)
    return spec


def _article(**overrides) -> dict:
    body = (
        "## How we compared SEO agencies\n\n"
        "We looked at how each agency reports results. The agencies below were chosen "
        "for transparent pricing. Every agency here offers monthly reporting, and two "
        "agencies include technical audits.\n\n"
        "## Top agencies\n\nEach agency is summarized with its strengths."
    )
    article = {
        "title": VALID_TITLE,
        "meta_title": VALID_TITLE,
        "meta_description": (
            "Compare seo agencies for small businesses: pricing, reporting and what to ask "
            "before you sign. Read the full guide to choose with confidence."
        ),
        "introduction": (
            "Choosing between seo agencies is hard when every proposal looks the same. "
            "This guide shows what separates them."
        ),
        "body_markdown": body,
        "focus_keyphrase": KEYPHRASE,
    }
    article.update(overrides)
    return article


# ── 1 + 2. title contract at generation time ─────────────────────────────────


def test_valid_title_fixture_is_actually_valid():
    assert TITLE_MIN_CHARS <= len(VALID_TITLE) <= TITLE_MAX_CHARS
    assert title_is_valid(VALID_TITLE, KEYPHRASE)


def test_title_missing_focus_keyphrase_is_invalid():
    title = "Best Marketing Partners for Small Businesses in Practice"
    assert TITLE_MIN_CHARS <= len(title) <= TITLE_MAX_CHARS
    assert "missing_focus_keyphrase" in title_violations(title, KEYPHRASE)


def test_keyphrase_variant_does_not_count_as_the_exact_keyphrase():
    # Singular / reordered forms are not the user's exact phrase.
    assert not contains_keyphrase("Choosing an SEO Agency for Your Business", KEYPHRASE)
    assert not contains_keyphrase("Agencies for SEO: A Buyer's Checklist", KEYPHRASE)
    # Case and punctuation differences are fine.
    assert contains_keyphrase("SEO-Agencies: compared", "seo agencies")


@pytest.mark.parametrize(
    "title",
    [
        "SEO Agencies Compared",  # too short
        "SEO Agencies for Small Businesses: A Very Long Buyer Guide With Extra Words",
    ],
)
def test_title_outside_length_range_is_invalid(title):
    assert not title_is_valid(title, KEYPHRASE)


def test_enforced_title_length_is_50_to_59_inclusive():
    assert (TITLE_MIN_CHARS, TITLE_MAX_CHARS) == (50, 59)
    base = "SEO Agencies "
    for length, valid in ((49, False), (50, True), (59, True), (60, False)):
        title = (base + "x" * 80)[:length]
        assert len(title) == length
        assert title_is_valid(title, KEYPHRASE) is valid, length


def test_topic_schema_and_prompt_state_59_not_60():
    from src.flow.model.structure import topics as topic_schema

    assert topic_schema.TITLE_MAX_CHARS == 59
    prompt = tg._build_system_prompt(
        keyphrase=KEYPHRASE,
        current_year=2026,
        selected_intent="commercial",
        selected_content_type="comparison",
    )
    assert "BETWEEN 50 AND 59" in prompt
    assert "60" not in prompt


def test_deterministic_repair_never_exceeds_59():
    for title in (
        "SEO Agencies for Small Businesses: How to Choose Wisely Now",  # 59
        "SEO Agencies for Small Businesses: How to Choose Wisely Today",  # 61
    ):
        repaired = repair_title(title, KEYPHRASE)
        assert repaired is not None and len(repaired) <= 59, repaired


def test_deterministic_repair_produces_a_compliant_title():
    for title in (
        "SEO Agencies Compared",
        "Marketing Partners for Small Businesses",
        "SEO Agencies for Small Businesses: A Very Long Buyer Guide With Extra Words",
    ):
        repaired = repair_title(title, KEYPHRASE)
        assert repaired is not None, title
        assert title_is_valid(repaired, KEYPHRASE), repaired


def _topics(*titles: str) -> SEOTopics:
    return SEOTopics(topics=[SEOTopic(title=t, recommended=(i == 0)) for i, t in enumerate(titles)])


@pytest.mark.asyncio
async def test_no_invalid_title_reaches_the_topic_picker():
    """Every title returned for display satisfies keyphrase + length, even when
    the model ignores both rules and the LLM repair pass fails too."""
    bad = _topics(
        "Marketing Partners for Small Businesses",  # no keyphrase, too short
        "SEO Agencies",  # too short
        VALID_TITLE,
    )
    model = AsyncMock()
    # First call: generation. Second call: LLM repair — raises, forcing the
    # deterministic net to do the work.
    model.ainvoke.side_effect = [bad, RuntimeError("repair model down")]

    result = await tg._generate_and_validate_topics(
        model=model, messages=[], query=KEYPHRASE, keyphrase=KEYPHRASE
    )

    assert result is not None
    assert result.topics
    for topic in result.topics:
        assert title_is_valid(topic.title, KEYPHRASE), topic.title
    assert sum(1 for topic in result.topics if topic.recommended) == 1


@pytest.mark.asyncio
async def test_regeneration_feedback_cannot_remove_the_focus_keyphrase():
    """User feedback that asks for a different keyword still yields titles with
    the user's original focus keyphrase."""
    regenerated = _topics(
        "Best Digital Marketing Firms for Small Businesses Today",
        "Top Growth Marketing Firms for Local Service Businesses",
    )
    model = AsyncMock()
    model.ainvoke.side_effect = [regenerated, RuntimeError("repair model down")]

    result = await tg._generate_and_validate_topics(
        model=model,
        messages=["feedback: use 'marketing firms' instead"],
        query=KEYPHRASE,
        keyphrase=KEYPHRASE,
    )

    assert result is not None
    for topic in result.topics:
        assert contains_keyphrase(topic.title, KEYPHRASE), topic.title


def test_system_prompt_states_keyphrase_content_type_and_intent():
    prompt = tg._build_system_prompt(
        keyphrase=KEYPHRASE,
        current_year=2026,
        selected_intent="commercial",
        selected_content_type="comparison",
    )
    assert f'"{KEYPHRASE}"' in prompt
    assert "comparison" in prompt and "commercial" in prompt
    assert f"{TITLE_MIN_CHARS} AND {TITLE_MAX_CHARS}" in prompt


# ── 3. user-selected title is locked ─────────────────────────────────────────


class _StructuredModelFactory:
    """Stands in for topic_generation_model(): returns a fixed structured model."""

    def __init__(self, model):
        self._model = model

    def with_structured_output(self, _schema):
        return self._model


@pytest.mark.asyncio
async def test_selected_topic_is_never_rewritten_at_selection(monkeypatch):
    """Even a selection that breaks the contract is used verbatim — repair only
    ever happens BEFORE the user picks."""
    odd_selection = "My Own Hand-Edited Title"
    assert not title_is_valid(odd_selection, KEYPHRASE)

    model = AsyncMock()
    model.ainvoke.return_value = _topics(
        VALID_TITLE, "SEO Agencies Pricing Explained for Small Business Owners"
    )
    monkeypatch.setattr(tg, "topic_generation_model", lambda: _StructuredModelFactory(model))
    monkeypatch.setattr(tg, "interrupt", lambda _payload: {"selected_topic": odd_selection})

    state = {
        "serp_normalized": {"query": KEYPHRASE},
        "seo_result": {"keyword_recommendations": {"selected_keyword": KEYPHRASE}},
        "content": {"content_type": "comparison"},
    }

    result = await tg.topic_generation(state)

    assert result["content"]["selected_topic"] == odd_selection
    assert result["content"]["focus_keyword"] == KEYPHRASE


def test_changed_title_is_reverted_to_the_user_selection():
    drifted = _article(title="SEO Agencies: The Ultimate 2026 Guide to Hiring the Best")

    enforced = enforce_onpage_seo(
        drifted, selected_title=VALID_TITLE, focus_keyphrase=KEYPHRASE, stage="test"
    )

    assert enforced["title"] == VALID_TITLE
    # Returned a copy — checkpointed state is not mutated in place.
    assert drifted["title"] != VALID_TITLE


def test_changed_title_fails_validation():
    result = check_selected_title_preserved(_article(title="Something Else Entirely"), _spec())
    assert not result["passed"] and result["severity"] == "blocking"
    assert check_selected_title_preserved(_article(), _spec())["passed"]


def test_repair_merge_cannot_blank_meta_description_or_change_title():
    """The repair model echoes the full schema; unwritten fields come back None."""
    original = _article()
    echoed = {
        "title": "SEO Agencies Reworded By The Repair Model For No Reason",
        "meta_description": None,
        "slug": None,
        "introduction": original["introduction"] + " Extra repaired sentence.",
    }

    merged = merge_preserving_existing(original, echoed)
    enforced = enforce_onpage_seo(merged, selected_title=VALID_TITLE, focus_keyphrase=KEYPHRASE)

    assert enforced["meta_description"] == original["meta_description"]
    assert enforced["introduction"].endswith("Extra repaired sentence.")
    assert enforced["title"] == VALID_TITLE


def test_title_differing_only_in_quotes_or_spacing_is_still_restored_exactly():
    """Normalizing both sides used to treat these as "unchanged" and ship them."""
    for drifted in (f'"{VALID_TITLE}"', VALID_TITLE.replace(" ", "  ", 1), f" {VALID_TITLE} "):
        enforced = enforce_onpage_seo(
            _article(title=drifted), selected_title=VALID_TITLE, focus_keyphrase=KEYPHRASE
        )
        assert enforced["title"] == VALID_TITLE


def test_model_written_meta_title_is_discarded_for_the_selected_title():
    """meta_title is what the editor used to display and save as the article
    title, so a model-authored one is exactly how the selection got replaced."""
    article = _article(meta_title="SEO Agencies: 9 Top Picks Reviewed and Ranked for 2026")
    assert not check_selected_title_preserved(article, _spec())["passed"]

    enforced = enforce_onpage_seo(article, selected_title=VALID_TITLE, focus_keyphrase=KEYPHRASE)

    assert enforced["meta_title"] == VALID_TITLE
    assert check_selected_title_preserved(enforced, _spec())["passed"]


@pytest.mark.asyncio
async def test_selected_title_is_identical_in_the_persisted_content(monkeypatch):
    """Selection -> generation -> repair -> humanization -> final validation ->
    persistence, with the model drifting the title at every stage: the saved
    title and meta title are byte-for-byte the selected title."""
    import uuid

    from src.flow.engines.content.generation import persist_content as persist_module
    from src.services import content_service as content_service_module
    from src.utils import loop_bridge

    selected = VALID_TITLE
    drifts = {
        "generate_content": ("SEO Agencies Guide: Choosing the Right Partner in 2026", "Meta A"),
        "targeted_repair": (
            f"{selected} ",
            "SEO Agencies Compared for Small Businesses and Startups",
        ),
        "humanize_content": ("seo agencies for small businesses: how to choose one", None),
        "final_validate_content": (f'"{selected}"', selected + "!"),
    }

    final_content = _article()
    for stage, (model_title, model_meta_title) in drifts.items():
        model_output = {"title": model_title, "meta_title": model_meta_title}
        final_content = merge_preserving_existing(final_content, model_output)
        final_content = enforce_onpage_seo(
            final_content, selected_title=selected, focus_keyphrase=KEYPHRASE, stage=stage
        )
        assert final_content["title"] == selected, stage
        assert final_content["meta_title"] == selected, stage

    # Even if some future node wrote a different title after the last lock,
    # persistence reads the selection itself.
    final_content["title"] = "A Different Title Written After The Last Lock Somehow"

    captured = {}

    class _FakeService:
        def __init__(self, _db):
            pass

        async def create_content(self, _workspace_id, _user_id, payload):
            captured["payload"] = payload
            return type("Saved", (), {"id": uuid.uuid4()})()

    class _FakeDb:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc):
            return False

    async def _run_inline(coro):
        return await coro

    monkeypatch.setattr(content_service_module, "ContentService", _FakeService)
    monkeypatch.setattr(loop_bridge, "run_on_main_loop", _run_inline)
    monkeypatch.setattr(
        "src.api.database.async_database.get_pooled_langgraph_db_context", lambda: _FakeDb()
    )

    state = {
        "serp_payload": {"user_id": str(uuid.uuid4()), "workspace_id": str(uuid.uuid4())},
        "content": {"selected_topic": selected, "final_content": final_content},
    }
    await persist_module.persist_content(state, {"configurable": {"thread_id": str(uuid.uuid4())}})

    payload = captured["payload"]
    assert payload.title == selected
    assert payload.seo_data.meta_title == selected


# ── 4. title / content subject alignment ─────────────────────────────────────


TOOLS_BODY = (
    "## The best SEO tools\n\n"
    "These tools help you track rankings. Each tool is compared on price. "
    "The tools below include crawlers, and the best tool for audits is listed first. "
    "Pick tools that integrate with your stack; a good tool saves hours.\n"
)


def test_agency_title_with_tools_body_is_a_mismatch():
    mismatch = find_subject_mismatch(VALID_TITLE, TOOLS_BODY)
    assert mismatch is not None
    assert mismatch["promised_class"] == "agency"
    assert mismatch["dominant_class"] == "tool"


def test_subject_mismatch_blocks_validation():
    article = _article(body_markdown=TOOLS_BODY)
    result = check_title_subject_alignment(article, _spec())
    assert not result["passed"] and result["severity"] == "blocking"
    assert "agency" in result["detail"] and "tool" in result["detail"]


def test_matching_subject_passes_and_generic_titles_are_not_guessed_at():
    assert check_title_subject_alignment(_article(), _spec())["passed"]
    assert (
        find_subject_mismatch("How to Do Keyword Research Step by Step for Beginners", TOOLS_BODY)
        is None
    )


# ── 5-7. keyphrase in meta description / introduction, meta required ────────


def test_missing_keyphrase_in_meta_description_fails_and_is_repaired():
    article = _article(meta_description="A practical look at pricing, reporting and contracts.")
    assert not check_focus_keyphrase_in_meta_description(article, _spec())["passed"]

    enforced = enforce_onpage_seo(article, selected_title=VALID_TITLE, focus_keyphrase=KEYPHRASE)
    assert contains_keyphrase(enforced["meta_description"], KEYPHRASE)
    assert check_focus_keyphrase_in_meta_description(enforced, _spec())["passed"]


def test_missing_keyphrase_in_introduction_fails_and_is_repaired():
    article = _article(introduction="Picking a marketing partner is hard. This guide helps.")
    assert not check_focus_keyphrase_in_introduction(article, _spec())["passed"]

    enforced = enforce_onpage_seo(article, selected_title=VALID_TITLE, focus_keyphrase=KEYPHRASE)
    assert contains_keyphrase(enforced["introduction"], KEYPHRASE)
    # Original prose is preserved, not replaced.
    assert "Picking a marketing partner is hard." in enforced["introduction"]


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_missing_meta_description_fails_and_is_always_regenerated(missing):
    article = _article(meta_description=missing)
    assert not check_meta_description_present(article, _spec())["passed"]

    enforced = enforce_onpage_seo(article, selected_title=VALID_TITLE, focus_keyphrase=KEYPHRASE)
    assert enforced["meta_description"].strip()
    assert len(enforced["meta_description"]) <= 160
    assert contains_keyphrase(enforced["meta_description"], KEYPHRASE)
    assert check_meta_description_present(enforced, _spec())["passed"]


def test_focus_keyphrase_in_title_check():
    assert check_focus_keyphrase_in_title(_article(), _spec())["passed"]
    result = check_focus_keyphrase_in_title(
        _article(title="Marketing Partners for Small Businesses Compared Here"), _spec()
    )
    assert not result["passed"]


def test_focus_keyphrase_is_the_users_not_the_models():
    article = _article(focus_keyphrase="best seo company")
    enforced = enforce_onpage_seo(article, selected_title=VALID_TITLE, focus_keyphrase=KEYPHRASE)
    assert enforced["focus_keyphrase"] == KEYPHRASE


# ── 8-9. JSON-LD exclusion + capped compensation ────────────────────────────


class _Level(Enum):
    INFO = 1
    WARNING = 2
    ERROR = 3


def _issue(element_type: str, message: str, level: _Level = _Level.ERROR) -> dict:
    return {
        "element_type": element_type,
        "message": message,
        "level": level,
        "details": "",
        "recommendation": "",
    }


def _run_seokar(raw_issues: list[dict], score: float) -> dict:
    report = {
        "issues": raw_issues,
        "seo_health": {"score": score},
        "basic_seo": {},
        "content_quality": {},
    }
    with patch.object(seokar_utils, "Seokar") as analyzer_cls:
        analyzer_cls.return_value.analyze.return_value = report
        return seokar_utils.calculate_seokar("<p>body</p>", title=VALID_TITLE)


def test_jsonld_errors_are_hidden_from_the_reported_issues():
    result = _run_seokar(
        [
            _issue("JSON-LD", "JSON-LD Parsing Error"),
            _issue("Structured Data", "No Common Structured Data Detected", _Level.INFO),
            _issue(
                "Structured Data (JSON-LD)", "Invalid JSON-LD Top-Level Structure", _Level.WARNING
            ),
            _issue("Meta Description", "Meta description too short", _Level.WARNING),
        ],
        score=80,
    )

    types = [issue["type"] for issue in result["issues"]]
    assert types == ["Meta Description"], types
    assert result["issue_summary"] == {"critical": 0, "errors": 0, "warnings": 1}


def test_non_jsonld_issues_are_not_hidden_or_compensated():
    result = _run_seokar(
        [
            _issue("Title", "Title too long", _Level.WARNING),
            _issue("Images", "Image missing alt text", _Level.ERROR),
        ],
        score=70,
    )
    assert len(result["issues"]) == 2
    assert result["seo_health_score"] == 70


def test_jsonld_exclusion_adds_two_points():
    result = _run_seokar([_issue("JSON-LD", "JSON-LD Parsing Error")], score=81)
    assert result["seo_health_score"] == 83


@pytest.mark.parametrize("base", [99, 100])
def test_jsonld_compensation_is_capped_at_100(base):
    result = _run_seokar([_issue("JSON-LD", "JSON-LD Parsing Error")], score=base)
    assert result["seo_health_score"] == 100


def test_readability_and_jsonld_compensation_together_never_exceed_100():
    result = _run_seokar(
        [
            _issue("readability", "Flesch reading ease low", _Level.WARNING),
            _issue("JSON-LD", "JSON-LD Parsing Error"),
        ],
        score=97,
    )
    assert result["seo_health_score"] == 100
