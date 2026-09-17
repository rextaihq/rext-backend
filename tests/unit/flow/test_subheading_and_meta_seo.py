"""Regression tests for the Yoast subheading and meta-description SEO fixes.

Pins the three reported Yoast findings, for every content type:

1. "Keyphrase in subheadings" — too few (or too many) H2/H3 headings reflect
   the focus keyphrase.
2. Meta description longer than 156 characters.
3. H2/H3 headings that are stubs or paragraph-length.

Plus the repair path: heading rewrites are validated, applied only when they
make nothing worse, and any failure leaves the article unchanged.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.flow.engines.content.generation import repair_content as repair_module
from src.flow.engines.content.generation import subheading_seo as sh
from src.flow.engines.content.generation.keyword_density import CONTENT_TYPE_FAMILIES
from src.flow.engines.content.generation.onpage_seo import (
    META_DESCRIPTION_MAX_CHARS,
    META_DESCRIPTION_MIN_CHARS,
    build_meta_description,
    enforce_onpage_seo,
    fit_meta_description,
    shorten_meta_description,
)
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.seo_title_rules import contains_keyphrase
from src.flow.engines.content.generation.validation import (
    CHECK_REGISTRY,
    FINAL_VALIDATE_CHECKS,
    check_meta_description_length,
    check_subheading_keyphrase,
    check_subheading_length,
)
from src.flow.model.structure.contents.base import BaseGeneratedContent, ContentBlock
from src.flow.prompts.system.content import CONTENT_SYSTEM_PROMPT

KEYPHRASE = "crm software"
TITLE = "CRM Software for Small Teams: How to Choose the Right One"
ALL_CONTENT_TYPES = sorted(CONTENT_TYPE_FAMILIES)


def _paragraph(topic: str, with_keyphrase: bool = True) -> str:
    lead = f"Good {KEYPHRASE} makes {topic} easier to manage. " if with_keyphrase else ""
    return lead + (
        f"Most small teams start {topic} with spreadsheets and shared inboxes, then notice "
        "that follow-ups slip and nobody knows who spoke to a customer last. A shared "
        "record of every conversation fixes that, as long as people actually keep it "
        "current. Start with the handful of fields your team uses every day, agree on "
        "who owns each stage, and review the pipeline together once a week so problems "
        "surface early instead of at the end of the quarter. Keep the setup simple at "
        "first and add automation only after the basic habits are in place."
    )


def _body(headings: list[str]) -> str:
    topics = ["tracking leads", "sales follow-ups", "customer support", "reporting", "onboarding"]
    parts = []
    for i, heading in enumerate(headings):
        parts.append(f"{heading}\n\n{_paragraph(topics[i % len(topics)], with_keyphrase=i < 3)}")
    return "\n\n".join(parts)


NON_MATCHING_H2S = [
    "## How Small Teams Track Their Leads Today",
    "## Setting Up Follow-Up Reminders That Stick",
    "## Handling Support Requests Without Chaos",
    "## Reports Worth Reading Every Monday",
]


def _article(headings: list[str] | None = None, **overrides) -> dict:
    article = {
        "title": TITLE,
        "meta_title": TITLE,
        "meta_description": (
            "Compare crm software for small teams: the features that matter, what it costs "
            "and how to roll it out. Read the full guide."
        ),
        "introduction": (
            f"Picking {KEYPHRASE} is easier once you know what your team actually needs. "
            "This guide walks through the choices that matter."
        ),
        "body_markdown": _body(headings if headings is not None else NON_MATCHING_H2S),
        "focus_keyphrase": KEYPHRASE,
    }
    article.update(overrides)
    return article


def _spec(content_type: str = "blog", keyphrase: str = KEYPHRASE, **outline_extra) -> dict:
    outline = {"title": TITLE, "focus_keyphrase": keyphrase, **outline_extra}
    return build_requirements_spec(outline, content_type, keyphrase, TITLE)


def _rewrites(*pairs: tuple[int, str]):
    async def _fn(request: dict) -> list[dict]:
        _fn.request = request
        return [{"index": i, "heading": h} for i, h in pairs]

    return _fn


# ── 1. keyphrase in H2/H3 ────────────────────────────────────────────────────


def test_h2_and_h3_are_extracted_but_h4_and_code_fences_are_not():
    body = (
        "## Choosing CRM Software for a Small Team\n\ntext\n\n"
        "### Pricing Tiers Compared\n\ntext\n\n"
        "#### A Deep Detail\n\ntext\n\n"
        "```\n## not a heading\n```\n"
    )
    headings = sh.extract_subheadings(body)
    assert [(h.level, h.text) for h in headings] == [
        (2, "Choosing CRM Software for a Small Team"),
        (3, "Pricing Tiers Compared"),
    ]


def test_too_few_subheadings_with_keyphrase_fails():
    result = check_subheading_keyphrase(_article(), _spec())
    assert not result["passed"]
    assert result["severity"] == "blocking"
    assert "0 of 4" in result["detail"]


def test_keyphrase_in_enough_subheadings_passes():
    headings = [
        "## How Small Teams Choose CRM Software",
        "## Setting Up Follow-Up Reminders That Stick",
        "## Rolling Out CRM Software Without Losing Data",
        "## Reports Worth Reading Every Monday",
    ]
    assert check_subheading_keyphrase(_article(headings), _spec())["passed"]


def test_keyphrase_in_every_subheading_is_flagged_as_stuffing():
    headings = [
        "## How Small Teams Choose CRM Software",
        "## CRM Software Reminders That Actually Stick",
        "## Rolling Out CRM Software Without Losing Data",
        "## CRM Software Reports Worth Reading",
    ]
    result = check_subheading_keyphrase(_article(headings), _spec())
    assert not result["passed"]
    assert "stuffing" in result["detail"]


@pytest.mark.parametrize(
    "total,expected",
    [(1, (1, 1)), (2, (1, 1)), (3, (1, 2)), (4, (2, 3)), (10, (3, 7)), (20, (6, 15))],
)
def test_keyphrase_heading_bounds_follow_yoast_30_to_75_percent(total, expected):
    assert sh.keyphrase_heading_bounds(total) == expected


def test_single_subheading_that_reflects_keyphrase_passes():
    article = _article(["## How Small Teams Choose CRM Software"])
    assert check_subheading_keyphrase(article, _spec())["passed"]


def test_no_subheadings_is_not_applicable():
    article = _article(body_markdown="Just prose with crm software and no headings.")
    result = check_subheading_keyphrase(article, _spec())
    assert result["passed"]
    assert "not applicable" in result["detail"]


# ── 2. synonyms and variations ──────────────────────────────────────────────


def test_reordered_words_and_function_words_count_as_a_variation():
    keyphrase = "software for crm"
    assert sh.heading_reflects_keyphrase("CRM Software Compared", keyphrase)
    assert sh.keyphrase_content_words(keyphrase) == ["software", "crm"]


def test_more_than_half_of_core_words_is_required():
    keyphrase = "best crm software startups"  # 4 content words -> 3 needed
    assert sh.heading_reflects_keyphrase("The Best CRM Software Picks", keyphrase)
    assert not sh.heading_reflects_keyphrase("The Best CRM Picks for You", keyphrase)
    # Two-word keyphrase: half is not enough.
    assert not sh.heading_reflects_keyphrase("Choosing Software Carefully", KEYPHRASE)


def test_word_matching_is_whole_word_not_substring():
    assert not sh.heading_reflects_keyphrase("CRMs and Softwares Explained", KEYPHRASE)


def test_explicit_synonyms_from_the_outline_are_credited():
    headings = [
        "## Choosing a Customer Relationship Platform",
        "## Setting Up Follow-Up Reminders That Stick",
        "## Moving Contacts Into a Customer Relationship Platform",
        "## Reports Worth Reading Every Monday",
    ]
    article = _article(headings)
    assert not check_subheading_keyphrase(article, _spec())["passed"]
    spec = _spec(keyphrase_synonyms=["customer relationship platform"])
    assert spec["keyphrase_synonyms"] == ["customer relationship platform"]
    assert check_subheading_keyphrase(article, spec)["passed"]


# ── 3. meta description length ──────────────────────────────────────────────


def _meta_of_length(n: int) -> str:
    base = "Compare crm software for small teams and learn which features matter most. "
    text = (base + "x" * 400)[:n]
    return text


@pytest.mark.parametrize(
    "length", [META_DESCRIPTION_MIN_CHARS, 140, 155, META_DESCRIPTION_MAX_CHARS]
)
def test_meta_description_within_limit_passes_and_is_untouched(length):
    meta = _meta_of_length(length)
    assert len(meta) == length
    article = _article(meta_description=meta)
    assert check_meta_description_length(article, _spec())["passed"]
    enforced = enforce_onpage_seo(article, selected_title=TITLE, focus_keyphrase=KEYPHRASE)
    assert enforced["meta_description"] == meta


def test_meta_description_of_157_characters_fails():
    article = _article(meta_description=_meta_of_length(157))
    result = check_meta_description_length(article, _spec())
    assert not result["passed"]
    assert result["severity"] == "blocking"


def test_meta_description_too_short_is_only_a_warning():
    result = check_meta_description_length(
        _article(meta_description="Short crm software."), _spec()
    )
    assert not result["passed"]
    assert result["severity"] == "warning"


def test_long_meta_description_drops_a_whole_sentence_and_keeps_the_cta():
    meta = (
        "Compare crm software for small teams by price, setup time and the features you will "
        "really use. We tested twelve tools over three months with real sales teams. "
        "Read the full guide."
    )
    assert len(meta) > META_DESCRIPTION_MAX_CHARS
    enforced = enforce_onpage_seo(
        _article(meta_description=meta), selected_title=TITLE, focus_keyphrase=KEYPHRASE
    )
    result = enforced["meta_description"]
    assert len(result) <= META_DESCRIPTION_MAX_CHARS
    assert result.endswith("Read the full guide.")
    assert contains_keyphrase(result, KEYPHRASE)
    assert "We tested twelve tools" not in result  # dropped as a whole sentence, not cut
    assert check_meta_description_length(enforced, _spec())["passed"]


def test_long_single_sentence_meta_description_is_cut_at_a_clause_not_mid_word():
    meta = (
        "Compare crm software for small teams by price, setup time, integrations, mobile apps, "
        "reporting and the quality of support, so you can pick a tool your whole team will use"
    )
    assert len(meta) > META_DESCRIPTION_MAX_CHARS
    result = shorten_meta_description(meta, KEYPHRASE)
    assert result is not None
    assert META_DESCRIPTION_MIN_CHARS <= len(result) <= META_DESCRIPTION_MAX_CHARS
    assert result.endswith(".")
    assert meta.startswith(result[:-1])
    assert contains_keyphrase(result, KEYPHRASE)


def test_unsplittable_meta_description_is_rebuilt_from_the_article():
    meta = "crm software " + " ".join(["reliable"] * 40)
    result = fit_meta_description(
        meta,
        focus_keyphrase=KEYPHRASE,
        title=TITLE,
        introduction=_article()["introduction"],
    )
    assert len(result) <= META_DESCRIPTION_MAX_CHARS
    assert contains_keyphrase(result, KEYPHRASE)


@pytest.mark.parametrize("intro_words", [5, 30, 80, 200])
@pytest.mark.parametrize(
    "keyphrase",
    [KEYPHRASE, "best crm software for small business teams with remote sales staff"],
)
def test_generated_meta_description_never_exceeds_the_limit(intro_words, keyphrase):
    introduction = " ".join(["Teams compare tools carefully."] * intro_words)
    result = build_meta_description(
        focus_keyphrase=keyphrase, title=TITLE, introduction=introduction
    )
    assert 0 < len(result) <= META_DESCRIPTION_MAX_CHARS
    assert contains_keyphrase(result, keyphrase)


def test_schema_and_system_prompt_state_the_156_limit():
    assert "156" in BaseGeneratedContent.model_fields["meta_description"].description
    assert "156" in CONTENT_SYSTEM_PROMPT
    assert "140–160" not in CONTENT_SYSTEM_PROMPT


# ── 4. heading length ───────────────────────────────────────────────────────


@pytest.mark.parametrize("heading", ["## Pricing", "## How It Works", "## FAQs"])
def test_very_short_h2_fails(heading):
    headings = [heading, *NON_MATCHING_H2S[1:]]
    result = check_subheading_length(_article(headings), _spec())
    assert not result["passed"]
    assert "too short" in result["detail"]


def test_very_short_h3_fails():
    body = "## Choosing CRM Software for a Small Team\n\ntext\n\n### Tips\n\ntext"
    result = check_subheading_length(_article(body_markdown=body), _spec())
    assert not result["passed"]
    assert "H3 'Tips'" in result["detail"]


def test_very_long_h2_and_h3_fail():
    long_h2 = (
        "## Everything a Growing Small Business Team Needs to Know Before It Commits to a Tool"
    )
    long_h3 = "### The Many Hidden Costs of Migration That Vendors Rarely Mention Up Front Today"
    body = f"{long_h2}\n\ntext\n\n{long_h3}\n\ntext"
    result = check_subheading_length(_article(body_markdown=body), _spec())
    assert not result["passed"]
    assert result["detail"].count("too long") == 2


def test_headings_inside_range_pass_and_lengths_may_vary():
    assert check_subheading_length(_article(), _spec())["passed"]
    lengths = {len(h.text) for h in sh.extract_subheadings(_article()["body_markdown"])}
    assert len(lengths) > 1


def test_question_headings_may_run_longer():
    question = "What Should a Small Team Look for When Comparing Customer Relationship Tools?"
    assert len(question) > sh.H2_LENGTH_RULE.max_chars
    assert sh.heading_length_issue(2, question) is None


def test_glossary_term_h3_is_not_forced_to_grow():
    body = "## Core Sales Terms Every Team Uses\n\ntext\n\n### CRM\n\nA definition."
    assert check_subheading_length(_article(body_markdown=body), _spec("glossary"))["passed"]
    assert not check_subheading_length(_article(body_markdown=body), _spec("blog"))["passed"]


# ── 5. long focus keyphrases ────────────────────────────────────────────────


def test_long_keyphrase_is_satisfied_by_its_core_words():
    keyphrase = "best crm software for small business teams"
    assert sh.keyphrase_fits_in_heading(keyphrase)
    assert sh.heading_reflects_keyphrase(
        "Choosing the Best CRM Software for Small Teams", keyphrase
    )


def test_keyphrase_too_long_for_any_heading_is_not_applicable():
    keyphrase = " ".join(
        f"extraordinarilylongword{i}" for i in range(12)
    )  # needs 7 words of 25 chars
    assert not sh.keyphrase_fits_in_heading(keyphrase)
    result = check_subheading_keyphrase(_article(), _spec(keyphrase=keyphrase))
    assert result["passed"]
    assert "keyphrase_too_long_for_heading" in result["detail"]


def test_prompt_instruction_uses_core_words_for_a_long_keyphrase():
    instruction = sh.build_subheading_prompt_instruction(
        "best crm software for small business teams"
    )
    assert "best, crm, software, small, business, teams" in instruction
    assert "do not repeat the full phrase" in instruction
    assert "30-75%" in instruction
    assert "20-70 characters" in instruction


def test_schema_heading_guidance_matches_the_enforced_rules():
    heading_doc = ContentBlock.model_fields["heading"].description
    body_doc = BaseGeneratedContent.model_fields["body_markdown"].description
    h2 = f"{sh.H2_LENGTH_RULE.min_chars}-{sh.H2_LENGTH_RULE.max_chars}"
    h3 = f"{sh.H3_LENGTH_RULE.min_chars}-{sh.H3_LENGTH_RULE.max_chars}"
    assert h2 in heading_doc and h2 in body_doc
    assert h3 in body_doc
    assert "30-75%" in heading_doc and "30-75%" in body_doc


# ── 6. all content types ────────────────────────────────────────────────────


def test_there_are_34_content_types():
    assert len(ALL_CONTENT_TYPES) == 34


def test_new_checks_run_before_and_after_humanization():
    for registry in (CHECK_REGISTRY, FINAL_VALIDATE_CHECKS):
        assert check_meta_description_length in registry
        assert check_subheading_keyphrase in registry
        assert check_subheading_length in registry


@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
async def test_every_content_type_is_validated_and_repaired_the_same_way(content_type):
    spec = _spec(content_type)
    article = _article(
        meta_description=(
            "Compare crm software for small teams by price, setup time and the features you "
            "will really use. We tested twelve tools with sales teams. Read the full guide."
        )
    )
    enforced = enforce_onpage_seo(article, selected_title=TITLE, focus_keyphrase=KEYPHRASE)
    assert check_meta_description_length(enforced, spec)["passed"]

    assert not check_subheading_keyphrase(enforced, spec)["passed"]
    rewrite = _rewrites(
        (0, "How Small Teams Track Leads in CRM Software"),
        (2, "Handling Support Requests Inside CRM Software"),
    )
    repaired = await sh.enforce_subheading_seo(
        enforced,
        focus_keyphrase=spec["target_keyword"],
        content_type=content_type,
        rewrite_fn=rewrite,
    )
    assert check_subheading_keyphrase(repaired, spec)["passed"], content_type
    assert check_subheading_length(repaired, spec)["passed"], content_type


# ── 7. repair behaviour and fail-safes ──────────────────────────────────────


async def test_rewrite_changes_only_heading_lines():
    article = _article()
    rewrite = _rewrites(
        (0, "How Small Teams Track Leads in CRM Software"),
        (2, "Handling Support Requests Inside CRM Software"),
    )
    repaired = await sh.enforce_subheading_seo(
        article, focus_keyphrase=KEYPHRASE, rewrite_fn=rewrite
    )

    before = article["body_markdown"].splitlines()
    after = repaired["body_markdown"].splitlines()
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(before) == len(after)
    assert all(before[i].startswith("## ") and after[i].startswith("## ") for i in changed)
    assert len(changed) == 2
    assert repaired["introduction"] == article["introduction"]
    assert "Make 2 more heading(s)" in rewrite.request["human"]
    assert check_subheading_keyphrase(repaired, _spec())["passed"]


async def test_compliant_article_makes_no_model_call():
    headings = [
        "## How Small Teams Choose CRM Software",
        "## Setting Up Follow-Up Reminders That Stick",
        "## Rolling Out CRM Software Without Losing Data",
        "## Reports Worth Reading Every Monday",
    ]
    article = _article(headings)
    rewrite = AsyncMock(return_value=[])
    result = await sh.enforce_subheading_seo(article, focus_keyphrase=KEYPHRASE, rewrite_fn=rewrite)
    assert result is article
    rewrite.assert_not_called()


async def test_overshooting_rewrites_are_not_applied_past_75_percent():
    rewrite = _rewrites(
        (0, "How Small Teams Track Leads in CRM Software"),
        (1, "Follow-Up Reminders That Stick in CRM Software"),
        (2, "Handling Support Requests Inside CRM Software"),
        (3, "Reading CRM Software Reports Every Monday"),
    )
    repaired = await sh.enforce_subheading_seo(
        _article(), focus_keyphrase=KEYPHRASE, rewrite_fn=rewrite
    )
    analysis = sh.analyze_subheading_keyphrase(
        sh.extract_subheadings(repaired["body_markdown"]), KEYPHRASE
    )
    assert analysis["status"] == "ok"
    assert analysis["matching"] <= analysis["max"]


@pytest.mark.parametrize(
    "bad_heading",
    [
        "CRM Software: How Small Teams Track Their Leads",  # bolted-on prefix
        "How Small Teams Track Their Leads - CRM Software",  # bolted-on suffix
        "Acme CRM Software for Tracking Leads",  # introduces the brand
        "CRM Software",  # too short
        "CRM Software Leads and CRM Software Tracking for Teams",  # repeated keyphrase
        "Choosing CRM Software Pricing Plans Carefully",  # loses the original meaning
    ],
)
async def test_unacceptable_rewrites_are_rejected(bad_heading):
    article = _article()
    original = sh.extract_subheadings(article["body_markdown"])[0]
    assert (
        sh.validate_heading_rewrite(original, bad_heading, keyphrase=KEYPHRASE, brand_name="Acme")
        is None
    )
    assert sh.validate_heading_rewrite(
        original,
        "How Small Teams Track Leads in CRM Software",
        keyphrase=KEYPHRASE,
        brand_name="Acme",
    )
    repaired = await sh.enforce_subheading_seo(
        article,
        focus_keyphrase=KEYPHRASE,
        brand_name="Acme",
        rewrite_fn=_rewrites((0, bad_heading)),
    )
    assert repaired["body_markdown"] == article["body_markdown"]


async def test_rewrite_that_breaks_an_expected_outline_section_is_rejected():
    article = _article()
    repaired = await sh.enforce_subheading_seo(
        article,
        focus_keyphrase=KEYPHRASE,
        expected_sections=["Support Requests"],
        rewrite_fn=_rewrites((2, "Answering Customers Quickly With CRM Software")),
    )
    assert "## Handling Support Requests Without Chaos" in repaired["body_markdown"]


async def test_rewrite_that_pushes_keyword_density_out_of_range_is_rejected():
    real_density = sh.analyze_keyword_density

    def fake_density(*, text, **kwargs):
        report = dict(real_density(text=text, **kwargs))
        report["status"] = "too_high" if "Inside CRM Software" in text else "ok"
        return report

    article = _article()
    with patch.object(sh, "analyze_keyword_density", side_effect=fake_density):
        repaired = await sh.enforce_subheading_seo(
            article,
            focus_keyphrase=KEYPHRASE,
            rewrite_fn=_rewrites(
                (0, "How Small Teams Track Leads in CRM Software"),
                (2, "Handling Support Requests Inside CRM Software"),
            ),
        )
    assert "## How Small Teams Track Leads in CRM Software" in repaired["body_markdown"]
    assert "Inside CRM Software" not in repaired["body_markdown"]


@pytest.mark.parametrize(
    "failure", [RuntimeError("model down"), asyncio.TimeoutError(), ValueError("bad json")]
)
async def test_rewrite_failure_keeps_the_article_unchanged(failure):
    article = _article()
    rewrite = AsyncMock(side_effect=failure)
    repaired = await sh.enforce_subheading_seo(
        article, focus_keyphrase=KEYPHRASE, rewrite_fn=rewrite
    )
    assert repaired["body_markdown"] == article["body_markdown"]


async def test_malformed_rewrite_output_is_ignored():
    article = _article()
    rewrite = AsyncMock(return_value=[{"index": "x"}, {"index": 99, "heading": "Nope"}, None, {}])
    repaired = await sh.enforce_subheading_seo(
        article, focus_keyphrase=KEYPHRASE, rewrite_fn=rewrite
    )
    assert repaired["body_markdown"] == article["body_markdown"]


async def test_too_long_heading_falls_back_to_deterministic_clause_trim():
    headings = [
        "## Choosing CRM Software: What Small Teams Should Compare Before Signing Anything",
        *NON_MATCHING_H2S[1:],
    ]
    article = _article(headings)
    rewrite = AsyncMock(side_effect=RuntimeError("model down"))
    repaired = await sh.enforce_subheading_seo(
        article, focus_keyphrase=KEYPHRASE, rewrite_fn=rewrite
    )
    assert "## Choosing CRM Software\n" in repaired["body_markdown"]
    assert check_subheading_length(repaired, _spec())["passed"]


async def test_short_heading_is_never_padded_deterministically():
    article = _article(["## Pricing", *NON_MATCHING_H2S[1:]])
    rewrite = AsyncMock(side_effect=RuntimeError("model down"))
    repaired = await sh.enforce_subheading_seo(
        article, focus_keyphrase=KEYPHRASE, rewrite_fn=rewrite
    )
    assert "## Pricing\n" in repaired["body_markdown"]


async def test_internal_error_returns_the_original_content():
    article = _article()
    with patch.object(sh, "subheading_report", side_effect=RuntimeError("boom")):
        result = await sh.enforce_subheading_seo(article, focus_keyphrase=KEYPHRASE)
    assert result is article


async def test_repair_node_fixes_heading_only_failures_without_full_article_repair():
    article = _article()
    failed = [check_subheading_keyphrase(article, _spec())]
    state = {
        "content": {
            "final_content": article,
            "outline": {"title": TITLE, "focus_keyphrase": KEYPHRASE},
            "content_type": "blog",
            "selected_topic": TITLE,
            "focus_keyword": KEYPHRASE,
            "review": {"validation": {"failed_checks": failed}, "repair_attempts": 0},
        }
    }
    # A real headings-only fix. repair_content now verifies a repair before
    # accepting it, so a stand-in that wiped the body ("## fixed") would rightly
    # be discarded as a regression of every body-level check.
    fixed = _article(
        [
            "## How Small Teams Track Leads in CRM Software",
            NON_MATCHING_H2S[1],
            "## Handling Support Requests Inside CRM Software",
            NON_MATCHING_H2S[3],
        ]
    )
    assert check_subheading_keyphrase(fixed, _spec())["passed"]
    with (
        patch.object(repair_module, "run_targeted_repair", new=AsyncMock()) as full_repair,
        patch.object(
            repair_module, "enforce_subheading_seo", new=AsyncMock(return_value=fixed)
        ) as heading_repair,
    ):
        result = await repair_module.repair_content(state)

    full_repair.assert_not_called()
    heading_repair.assert_awaited_once()
    assert heading_repair.await_args.kwargs["focus_keyphrase"] == KEYPHRASE
    assert result["content"]["final_content"] == fixed
    assert result["content"]["review"]["repair_attempts"] == 1


async def test_post_humanize_validation_repairs_headings_and_meta_before_reporting():
    from src.flow.engines.content.generation import validation as validation_module

    long_meta = (
        "Compare crm software for small teams by price, setup time and the features you will "
        "really use. We tested twelve tools over three months with real sales teams. "
        "Read the full guide."
    )
    state = {
        "content": {
            "final_content": _article(meta_description=long_meta),
            "outline": {"title": TITLE, "focus_keyphrase": KEYPHRASE},
            "content_type": "landing-page",
            "selected_topic": TITLE,
            "focus_keyword": KEYPHRASE,
            "review": {},
        }
    }
    rewrite = _rewrites(
        (0, "How Small Teams Track Leads in CRM Software"),
        (2, "Handling Support Requests Inside CRM Software"),
    )
    with (
        patch.object(sh, "_llm_rewrite", new=rewrite),
        patch.object(validation_module, "run_targeted_repair", new=AsyncMock(return_value=None)),
    ):
        result = await validation_module.final_validate_content(state)

    final = result["content"]["final_content"]
    report = result["content"]["review"]["final_validation"]
    failed = {c["name"] for c in report["failed_checks"]}
    assert len(final["meta_description"]) <= META_DESCRIPTION_MAX_CHARS
    assert not failed & {"meta_description_length", "subheading_keyphrase", "subheading_length"}
