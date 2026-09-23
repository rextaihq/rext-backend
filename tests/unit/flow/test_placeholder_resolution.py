"""Regression tests: draft placeholders are resolved, never carried or invented.

The outline is deliberately a DRAFT. `generate_outline` runs with no search tool,
so when it has nothing real to name it invents "Agency A", "Product B", "Tool 1".
That is expected there. The content-generation agent is what turns the draft into
real content using its research tools — and it could not, because:

1. `outline_entity_names` did not filter placeholders, so `resolve_targets` looked
   them up against stored competitor domains. `domain_matches` falls back to a
   prefix test, so "Agency A" matched `agencyanalytics.com` and "Product A"
   matched `producthunt.com`: pages from UNRELATED real companies came back
   stamped as that placeholder's official facts, were injected into the writer's
   prompt under "VERIFIED CURRENT PRODUCT FACTS — OFFICIAL SOURCES", and then
   corroborated invented pricing claims through `ClaimEvidence`. Two of the three
   available research calls were also spent on entities that do not exist.
2. Nothing told the writer the names were provisional. The prompt says the
   opposite ("STRUCTURE FIDELITY — CRITICAL: follow the EXACT structure").
3. The writer never received the workspace's real competitor list, even though
   `generate_content` already fetches it and threw the brand name away.

Detection was also incomplete (body only, never re-measured after humanization)
and flagged real products whose names end in the same shape ("Adobe Creative
Suite 6").
"""

from __future__ import annotations

import pytest

from src.flow.engines.content.generation.claim_integrity import (
    build_claim_evidence,
    outline_entity_names,
    outline_placeholder_names,
)
from src.flow.engines.content.generation.content_generation import (
    _format_draft_entities_for_prompt,
)
from src.flow.engines.content.generation.entity_research import resolve_targets
from src.flow.engines.content.generation.outline import _format_serp_entities
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.validation import (
    FINAL_VALIDATE_CHECKS,
    check_placeholder_product_names,
)
from src.flow.model.structure.outlines.product_names import find_placeholder_names_in_text

BRAND = {
    "brand_name": "Rankwell",
    "brand_url": "https://rankwell.io",
    "about": "Rankwell turns a keyword into a brief, a draft and a published post.",
    "selling_position": "For lean in-house teams.",
}

# One draft outline per product-naming schema, shaped the way each schema nests
# its entity names. Each mixes placeholders with REAL names, so a test that
# simply dropped everything would fail too.
DRAFT_OUTLINES = {
    "comparison": (
        {"products": [{"name": "Product A"}, {"name": "Product B"}, {"name": "Ahrefs"}]},
        ["Product A", "Product B"],
        ["Ahrefs"],
    ),
    "best-tools": (
        {
            "rankings": {
                "ranked_tools": [{"tool": {"name": "Tool 1"}}, {"tool": {"name": "Semrush"}}]
            }
        },
        ["Tool 1"],
        ["Semrush"],
    ),
    "alternatives": (
        {
            "alternatives_list": {"competitors": [{"name": "Vendor A"}]},
            "pricing": {"competitor_name": "Moz Pro"},
        },
        ["Vendor A"],
        ["Moz Pro"],
    ),
    "product-roundup": (
        {"products": [{"name": "Product A"}, {"name": "Notion"}]},
        ["Product A"],
        ["Notion"],
    ),
    "in-depth-review": (
        {
            "hero": {"product_name": "Product A"},
            "alternatives": {"alternatives": [{"name": "Option 2"}]},
        },
        ["Product A", "Option 2"],
        [],
    ),
    "pros-cons": ({"hero": {"product_name": "Surfer SEO"}}, [], ["Surfer SEO"]),
    "buying-guide": (
        {"options": [{"name": "Solution One"}, {"name": "Frase"}]},
        ["Solution One"],
        ["Frase"],
    ),
    "resource-list": (
        {"categories": [{"resources": [{"name": "Tool 1"}, {"name": "Zoho CRM Plus"}]}]},
        ["Tool 1"],
        ["Zoho CRM Plus"],
    ),
}


# ── 1. a draft may legitimately carry placeholders, across every schema ──────


@pytest.mark.parametrize("content_type", sorted(DRAFT_OUTLINES))
def test_draft_placeholders_are_identified_per_schema(content_type):
    outline, expected_drafts, expected_real = DRAFT_OUTLINES[content_type]
    assert sorted(outline_placeholder_names(outline)) == sorted(expected_drafts)
    assert sorted(outline_entity_names(outline)) == sorted(expected_real)


def test_the_two_views_partition_the_same_walk():
    """Neither view may invent or lose a name the other one saw."""
    for outline, drafts, real in DRAFT_OUTLINES.values():
        combined = set(outline_entity_names(outline)) | set(outline_placeholder_names(outline))
        assert combined == set(drafts) | set(real)
        assert not set(outline_entity_names(outline)) & set(outline_placeholder_names(outline))


def test_real_product_containing_a_category_word_is_not_a_placeholder():
    """'Zoho CRM Plus' and 'Surfer SEO' are real; deleting them would be worse
    than the placeholder the filter is trying to catch."""
    outline = {"products": [{"name": "Zoho CRM Plus"}, {"name": "Surfer SEO"}, {"name": "Tool 1"}]}
    assert outline_placeholder_names(outline) == ["Tool 1"]
    assert outline_entity_names(outline) == ["Zoho CRM Plus", "Surfer SEO"]


# ── 2. research no longer mis-targets (the evidence-laundering regression) ───


def test_placeholders_are_never_researched_against_a_real_domain():
    outline = {"products": [{"name": "Agency A"}, {"name": "Ahrefs"}, {"name": "Product B"}]}
    targets = resolve_targets(
        outline, BRAND, ["agencyanalytics.com", "ahrefs.com", "producthunt.com"]
    )
    researched = {t.name for t in targets}
    assert researched == {"Rankwell", "Ahrefs"}
    assert "Agency A" not in researched
    assert "Product B" not in researched


@pytest.mark.parametrize(
    "placeholder, real_domain",
    [
        ("Agency A", "agencyanalytics.com"),
        ("Product A", "producthunt.com"),
        ("Company B", "companycam.com"),
        ("Tool 1", "toolkit.io"),
    ],
)
def test_each_known_mis_match_is_closed(placeholder, real_domain):
    """These all matched `domain_matches` and were researched as if real."""
    outline = {"products": [{"name": placeholder}]}
    assert resolve_targets(outline, None, [real_domain]) == []


def test_placeholders_never_become_claim_evidence_entities():
    outline = {"products": [{"name": "Product B"}, {"name": "Ahrefs"}]}
    evidence = build_claim_evidence(outline=outline, brand_context=BRAND, generation_meta={})
    assert "Product B" not in evidence["entity_names"]
    assert "Ahrefs" in evidence["entity_names"]


# ── 3. the agent is equipped to resolve them ────────────────────────────────


def test_prompt_names_the_drafts_and_the_real_alternatives():
    outline = {"products": [{"name": "Agency A"}, {"name": "Product B"}]}
    block = _format_draft_entities_for_prompt(
        outline, "Rankwell", ["ahrefs.com", "semrush.com"], "Rankwell"
    )
    assert "Agency A" in block and "Product B" in block
    # The workspace's real competitor list, which generation used to discard.
    assert "Ahrefs" in block and "Semrush" in block
    # ...and the safe failure, never a substitution.
    assert "COVER FEWER PRODUCTS" in block
    assert "Never invent a name" in block


def test_prompt_block_is_absent_when_the_outline_is_already_real():
    outline = {"products": [{"name": "Ahrefs"}, {"name": "Semrush"}]}
    assert _format_draft_entities_for_prompt(outline, "Rankwell", ["ahrefs.com"], "Rankwell") == ""


def test_prompt_block_still_appears_without_a_workspace_competitor_list():
    """A new workspace has no stored competitors — the writer must still be told
    the names are drafts, and sent to search_tool instead."""
    outline = {"products": [{"name": "Agency A"}]}
    block = _format_draft_entities_for_prompt(outline, "", [], "")
    assert "Agency A" in block
    assert "search_tool" in block


def test_serp_titles_are_available_as_a_fallback_entity_source():
    results = [
        {"title": "14 Best Project Management Tools for 2026", "domain": "asana.com"},
        {"title": "", "domain": "skipped.com"},
        "not-a-dict",
    ]
    formatted = _format_serp_entities(results)
    assert "14 Best Project Management Tools for 2026" in formatted
    assert "asana.com" in formatted
    assert "skipped.com" not in formatted
    assert _format_serp_entities([]) == "None available."


# ── 4. detection is complete and trustworthy ────────────────────────────────


def _spec(outline=None):
    return build_requirements_spec(
        outline if outline is not None else {}, "comparison", "seo tools", "Title"
    )


@pytest.mark.parametrize(
    "content",
    [
        pytest.param({"body_markdown": "Product A is cheaper."}, id="body"),
        pytest.param({"introduction": "Product A leads."}, id="introduction"),
        pytest.param({"title": "Product A vs Ahrefs"}, id="title"),
        pytest.param({"meta_description": "We compare Product A."}, id="meta_description"),
        pytest.param({"cta": {"text": "Try Product A now"}}, id="cta"),
    ],
)
def test_placeholder_is_caught_on_every_visible_surface(content):
    assert not check_placeholder_product_names(content, _spec())["passed"]


def test_surviving_draft_name_is_named_as_such():
    outline = {"products": [{"name": "Product A"}, {"name": "Ahrefs"}]}
    result = check_placeholder_product_names(
        {"body_markdown": "Product A costs less than Ahrefs."}, _spec(outline)
    )
    assert not result["passed"]
    assert "came straight from the approved outline" in result["detail"]
    assert "Product A" in result["detail"]


def test_clean_article_passes():
    content = {
        "title": "Ahrefs vs Semrush",
        "introduction": "Both are strong.",
        "body_markdown": "## How they differ\n\nAhrefs leads on backlinks.",
    }
    assert check_placeholder_product_names(content, _spec())["passed"]


def test_placeholder_check_runs_after_humanization():
    """Humanization rewrites the body wholesale; measuring only pre-humanize
    meant a placeholder it preserved was never looked at again."""
    assert check_placeholder_product_names in FINAL_VALIDATE_CHECKS


# ── 5. no false positives — a real product must never be called fabricated ──


@pytest.mark.parametrize(
    "text",
    [
        "Adobe Creative Suite 6 was the last perpetual licence.",
        "Atlassian Compass Platform 2 launched last year.",
        "Microsoft Power Platform A/B testing is limited.",
        "Google Analytics 4 replaced Universal Analytics.",
        "Windows 11 and macOS 15 are both supported.",
        "Zoho CRM Plus bundles eight applications.",
        "The Notion API v2 changed how databases are queried.",
        "Our Tier 2 support plan includes onboarding.",
        "pick the tool a beginner can learn",
        "Use the Slack App Directory to install it.",
    ],
)
def test_real_product_names_are_not_flagged(text):
    assert find_placeholder_names_in_text(text) == []
    assert check_placeholder_product_names({"body_markdown": text}, _spec())["passed"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Product A handles briefing; Product B publishes.", ["Product A", "Product B"]),
        ("Agency C sits between the two and Tool 1 reports.", ["Agency C", "Tool 1"]),
        ("Compare Option 2 against Vendor B before you commit.", ["Option 2", "Vendor B"]),
        ("## Tool 1 overview", ["Tool 1"]),
        ("- Company A offers the widest integrations.", ["Company A"]),
        ("We recommend Solution One for enterprise buyers.", ["Solution One"]),
    ],
)
def test_true_positives_survive_the_tightening(text, expected):
    assert find_placeholder_names_in_text(text) == expected


# ── 6. nothing fabricates a replacement ─────────────────────────────────────


def test_unresolvable_placeholder_is_reported_not_renamed():
    """No stage may substitute a guessed product. The placeholder stays visible
    in the report, and the outline it came from is left untouched."""
    outline = {"products": [{"name": "Agency A"}]}
    before = [p["name"] for p in outline["products"]]

    assert resolve_targets(outline, None, []) == []
    assert outline_placeholder_names(outline) == ["Agency A"]
    result = check_placeholder_product_names({"body_markdown": "Agency A wins."}, _spec(outline))

    assert not result["passed"]
    assert "Agency A" in result["detail"]
    assert "do not rename these to another guess" in result["detail"]
    assert [p["name"] for p in outline["products"]] == before
