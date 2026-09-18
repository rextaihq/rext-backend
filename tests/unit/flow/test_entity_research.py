"""Official-source product research within the article's Tavily budget.

Pins the cause of wrong product facts in generated content — nothing looked up
the promoted brand or the named products on their own sites, so stale
third-party plan tables and a missing release status (alpha) went into the
article — and the constraint the fix must respect: research spends from the SAME
per-article search budget as the writer's search_tool (SEARCH_HARD_CAP, 6), so the
article never makes more than 6 Tavily calls.

Tavily is mocked throughout.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
from src.flow.engines.agent.tools.tools import SEARCH_HARD_CAP
from src.flow.engines.content.generation import entity_research as er
from src.flow.engines.content.generation.claim_integrity import find_unsupported_claims
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.prompts.system.factual_integrity import FACTUAL_INTEGRITY_RULES

BRAND = {"brand_name": "Nextly", "brand_url": "https://nextlyhq.com"}
OUTLINE = {"products": [{"name": "Nextly"}, {"name": "Builder.io"}, {"name": "Strapi"}]}
COMPETITOR_DOMAINS = ["builder.io", "strapi.io"]

PRICING_TABLE = (
    "Free $0 per user/mo. Pro $24 per user/mo billed annually (or $30 monthly). "
    "Team $40 per user/mo billed annually."
)
ALPHA_NOTE = "Nextly is in alpha. The published release is 0.0.2-alpha.62."


class _FakeSearch:
    """Stands in for TavilySearch and records every call made."""

    calls: list[dict] = []
    results: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def ainvoke(self, query):
        _FakeSearch.calls.append({"query": query, **self.kwargs})
        return {"results": _FakeSearch.results}


@pytest.fixture
def tavily():
    _FakeSearch.calls = []
    _FakeSearch.results = [
        {
            "url": "https://nextlyhq.com/blog/nextly-alpha",
            "title": "Nextly Alpha",
            "content": ALPHA_NOTE,
        },
        {
            "url": "https://www.builder.io/pricing",
            "title": "Pricing",
            "content": PRICING_TABLE,
            "published_date": "2026-09-01",
        },
        {
            "url": "https://forum.builder.io/t/seats-and-pricing/4764",
            "title": "Seats?",
            "content": "Growth plan is $49/month",
        },
        {
            "url": "https://www.g2.com/products/builder-io/pricing",
            "title": "G2",
            "content": "Builder.io Growth $49",
        },
        {
            "url": "https://strapi.io/pricing-cloud",
            "title": "Strapi Cloud",
            "content": "Essential $15/month",
        },
    ]
    with patch.object(er, "TavilySearch", _FakeSearch):
        yield


# ── budget ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_research_spends_from_the_shared_six_call_budget(tavily):
    search_count = [0]
    await er.research_official_facts(OUTLINE, BRAND, COMPETITOR_DOMAINS, search_count)

    # One call per product, each only on that product's own domain, brand first.
    assert [c["include_domains"] for c in _FakeSearch.calls] == [
        ["nextlyhq.com"],
        ["builder.io"],
        ["strapi.io"],
    ]
    assert search_count == [3]
    # The writer keeps the calls its required queries need; total stays at the cap.
    assert SEARCH_HARD_CAP - search_count[0] >= er.WRITER_RESERVED_CALLS


@pytest.mark.asyncio
async def test_products_past_the_research_budget_are_not_researched(tavily):
    many = {"products": [{"name": n} for n in ("Builder.io", "Strapi", "Sanity", "Contentful")]}
    domains = ["builder.io", "strapi.io", "sanity.io", "contentful.com"]
    search_count = [0]
    await er.research_official_facts(many, BRAND, domains, search_count)

    researched = [c["include_domains"][0] for c in _FakeSearch.calls]
    assert researched == ["nextlyhq.com", "builder.io", "strapi.io"]  # brand first
    assert search_count == [SEARCH_HARD_CAP - er.WRITER_RESERVED_CALLS]


@pytest.mark.asyncio
@pytest.mark.parametrize(("used", "expected_calls"), [(2, 1), (3, 0), (SEARCH_HARD_CAP, 0)])
async def test_research_never_takes_the_writers_reserved_calls(tavily, used, expected_calls):
    search_count = [used]
    await er.research_official_facts(OUTLINE, BRAND, COMPETITOR_DOMAINS, search_count)
    assert len(_FakeSearch.calls) == expected_calls
    assert search_count[0] == used + expected_calls <= SEARCH_HARD_CAP


@pytest.mark.asyncio
async def test_nothing_to_research_costs_nothing(tavily):
    search_count = [0]
    blog = {"sections": [{"heading": "Why SEO matters"}]}
    assert await er.research_official_facts(blog, None, [], search_count) == []
    assert search_count == [0] and _FakeSearch.calls == []


def test_writer_is_told_the_remaining_budget_not_a_fixed_six():
    middleware = PersonaInjectionMiddleware(counters={"search": [3]})
    prompt = middleware._build_full_content_prompt(None, {"title": "t"}, 1500, "comparison")
    assert "Max **3 calls total**" in prompt
    assert "Max **6 calls total**" not in prompt


# ── targets ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("domain", "name", "expected"),
    [
        ("https://www.builder.io/pricing", "Builder.io", True),
        ("payloadcms.com", "Payload CMS", True),
        ("docs.strapi.io", "Strapi", True),
        ("webflow.com", "Webflow CMS", True),
        ("g2.com", "Builder.io", False),
        ("toolradar.com", "Strapi", False),
    ],
)
def test_domain_matching(domain, name, expected):
    assert er.domain_matches(domain, name) is expected


def test_targets_are_the_brand_plus_named_products_with_known_domains_for_any_outline():
    best_tools = {
        "rankings": [
            {"ranked_tools": [{"tool": {"name": "Sanity"}}, {"tool": {"name": "Unknowncms"}}]}
        ]
    }
    targets = er.resolve_targets(best_tools, BRAND, ["sanity.io"])
    assert targets == [
        er.ResearchTarget("Nextly", "nextlyhq.com", True),
        er.ResearchTarget("Sanity", "sanity.io"),
    ]


# ── what is kept ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_only_vendor_published_pages_become_official_facts(tavily):
    records = await er.research_official_facts(OUTLINE, BRAND, COMPETITOR_DOMAINS, [0])
    by_url = {r["url"]: r for r in records}

    assert set(by_url) == {
        "https://nextlyhq.com/blog/nextly-alpha",
        "https://www.builder.io/pricing",
        "https://strapi.io/pricing-cloud",
    }  # no forum post, no third-party price tracker, each page kept once, under its own product
    assert by_url["https://nextlyhq.com/blog/nextly-alpha"]["is_brand"] is True
    builder = by_url["https://www.builder.io/pricing"]
    assert builder["entity"] == "Builder.io" and builder["published_date"] == "2026-09-01"
    assert len(builder["snippet"]) <= er.EVIDENCE_TEXT_MAX_CHARS


@pytest.mark.asyncio
async def test_research_never_breaks_generation():
    class _Failing:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, query):
            raise RuntimeError("quota")

    with patch.object(er, "TavilySearch", _Failing):
        assert await er.research_official_facts(OUTLINE, BRAND, COMPETITOR_DOMAINS, [0]) == []


# ── what the writer and validation receive ──────────────────────────────────


@pytest.mark.asyncio
async def test_prompt_block_labels_official_sources_and_the_brand(tavily):
    records = await er.research_official_facts(OUTLINE, BRAND, COMPETITOR_DOMAINS, [0])
    block = er.format_official_facts_for_prompt(records)
    assert "VERIFIED CURRENT PRODUCT FACTS" in block
    assert "## Nextly (official site: nextlyhq.com) — the brand being promoted" in block
    assert "## Builder.io (official site: builder.io)" in block
    assert ALPHA_NOTE in block and PRICING_TABLE in block
    assert er.format_official_facts_for_prompt([]) == ""


def test_rules_make_official_facts_the_authority_for_every_content_type():
    for requirement in (
        "VERIFIED CURRENT PRODUCT FACTS",
        "billed annually",
        "release status",
        "top rated",
        "overall fit",
    ):
        assert requirement in FACTUAL_INTEGRITY_RULES


@pytest.mark.asyncio
async def test_official_facts_are_ground_truth_for_claim_validation(tavily):
    records = await er.research_official_facts(OUTLINE, BRAND, COMPETITOR_DOMAINS, [0])
    spec = build_requirements_spec(
        {**OUTLINE, "promote_brand": True, "brand_voice_promotion": BRAND},
        "comparison",
        "headless cms",
        "Nextly vs Builder.io",
        generation_meta={"searched_results": records},
    )
    evidence = spec["claim_evidence"]

    current = "Builder.io Pro costs $24 per user per month, billed annually."
    assert find_unsupported_claims(current, evidence) == []

    outdated = "Builder.io's Growth plan costs $49 per month."
    assert [c.category for c in find_unsupported_claims(outdated, evidence)] == ["pricing"]
