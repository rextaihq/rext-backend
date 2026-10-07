"""Factual-claim integrity across content types.

Each test pins a claim a reader could be misled by, written against what
the check sees in the finished article: an outdated competitor price, a stat
nobody sourced, an invented "we tested" story, an unsupported "best/leads/
winner" verdict, a made-up competitor weakness or brand integration. The
paired cases pin what must still pass: sourced facts, approved brand facts,
the author's real background and fit-based brand promotion.

The rules are global, so the same fixtures run against every content type.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
from src.flow.engines.content.generation import claim_integrity, validation
from src.flow.engines.content.generation.brand_placement_policy import BRAND_PLACEMENT_POLICY
from src.flow.engines.content.generation.claim_integrity import (
    find_unsupported_claims,
    outline_entity_names,
)
from src.flow.engines.content.generation.repair_content import (
    _build_brand_block,
    _build_sources_block,
)
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.validation import (
    CHECK_REGISTRY,
    FINAL_VALIDATE_CHECKS,
    check_unsupported_claims,
)
from src.flow.prompts.system.humanize import HUMANIZE_SYSTEM_PROMPT

BRAND = {
    "brand_name": "Nextly",
    "brand_url": "https://nextlyhq.com",
    "about": "Nextly is an open-source, TypeScript-first headless CMS built on Next.js "
    "with a visual page builder. Teams using Nextly cut publishing time by 45%.",
    "selling_position": "The headless CMS for TypeScript teams who want visual editing.",
}

CONTENTFUL_PRICING = {
    "url": "https://www.contentful.com/pricing/",
    "title": "Contentful pricing",
    "snippet": "Contentful pricing. Free plan available. The Lite plan starts at $300 per month.",
}
STRAPI_DOCS = {
    "url": "https://docs.strapi.io/cms/features/content-manager",
    "title": "Strapi Content Manager",
    "snippet": "Strapi does not support visual page editing in the Content Manager; "
    "editing is form based.",
}
W3TECHS = {
    "url": "https://w3techs.com/technologies/overview/content_management",
    "title": "Usage statistics of content management systems",
    "snippet": "WordPress is the most popular CMS, used by 43.2% of all websites.",
}
NODE_DOCS = {
    "url": "https://nextjs.org/docs/app/getting-started/installation",
    "title": "Installation | Next.js",
    "snippet": "System requirements: Node.js version 18.18 or later.",
}
SURVEY = {
    "url": "https://example-research.org/headless-cms-report",
    "title": "Headless CMS adoption report",
    "snippet": "73% of enterprises surveyed plan to adopt a headless CMS within two years.",
}

AUTHOR_PROFILE = "Jane Doe\nContent engineer\nHeadless CMS migrations\nJane has 8 years of experience building headless sites."

ALL_CONTENT_TYPES = sorted(BRAND_PLACEMENT_POLICY)


def _outline(content_type: str, **extra) -> dict:
    outline = {
        "title": "Nextly vs Contentful vs Strapi",
        "promote_brand": True,
        "brand_voice_promotion": BRAND,
        "products": [{"name": "Nextly"}, {"name": "Contentful"}, {"name": "Strapi"}],
    }
    outline.update(extra)
    return outline


def _spec(content_type: str, searched=(), author_profile: str = "", **outline_extra) -> dict:
    return build_requirements_spec(
        _outline(content_type, **outline_extra),
        content_type,
        "headless cms",
        "Nextly vs Contentful vs Strapi",
        generation_meta={"searched_results": list(searched), "author_profile": author_profile},
    )


def _article(body: str, introduction: str = "") -> dict:
    return {
        "title": "Nextly vs Contentful vs Strapi",
        "meta_description": "Compare headless cms options for TypeScript teams.",
        "introduction": introduction,
        "body_markdown": body,
    }


def _check(content_type: str, body: str, **spec_kwargs) -> dict:
    return check_unsupported_claims(_article(body), _spec(content_type, **spec_kwargs))


def _flagged(result: dict) -> str:
    assert not result["passed"], "expected the unsupported claim to be flagged"
    assert result["severity"] == "blocking"
    return result["detail"]


# ── wiring ───────────────────────────────────────────────────────────────────


def test_check_runs_before_and_after_humanization():
    assert check_unsupported_claims in CHECK_REGISTRY
    assert check_unsupported_claims in FINAL_VALIDATE_CHECKS
    assert "unsupported_claims" in validation._FINAL_REPAIRABLE_CLAIM_CHECKS


def test_policy_table_covers_all_34_content_types():
    assert len(ALL_CONTENT_TYPES) == 34


@pytest.mark.parametrize("content_type", ALL_CONTENT_TYPES)
def test_same_rules_apply_to_every_content_type(content_type):
    """No per-type exemption: an invented competitor price is wrong everywhere,
    and a sourced one is fine everywhere."""
    invented = _check(content_type, "Strapi Cloud costs $29/month for the Pro tier.")
    assert "[pricing]" in _flagged(invented)

    sourced = _check(
        content_type,
        "Contentful's Lite plan starts at $300 per month.",
        searched=[CONTENTFUL_PRICING],
    )
    assert sourced["passed"], sourced["detail"]


# ── comparison (the reported example) ────────────────────────────────────────


def test_comparison_flags_outdated_price_fabricated_experience_and_winner_claims():
    body = (
        "## Pricing compared\n\n"
        "Contentful's Lite plan starts at $489 per month, which prices out small teams.\n"
        "When I migrated 40 client sites to Nextly, load times dropped 60%.\n"
        "Nextly is the best headless CMS on the market.\n"
        "Our clear winner is Nextly.\n"
    )
    detail = _flagged(_check("comparison", body, searched=[CONTENTFUL_PRICING]))
    assert "$489" in detail  # retrieved source says $300 — the draft's figure is outdated
    assert "[fabricated_experience]" in detail
    assert "[absolute_superlative]" in detail and "clear winner" in detail


def test_comparison_allows_strong_but_supported_brand_positioning():
    body = (
        "## How Nextly differs\n\n"
        "Nextly is the best fit for TypeScript teams that want a visual page builder.\n"
        "Because Nextly is built on Next.js, front-end teams stay in one stack.\n"
        "Nextly lacks the plugin catalogue WordPress has, so budget for custom work.\n"
        "Teams using Nextly cut publishing time by 45%.\n"
        "Contentful's Lite plan starts at $300 per month.\n"
    )
    result = _check("comparison", body, searched=[CONTENTFUL_PRICING])
    assert result["passed"], result["detail"]


def test_comparison_competitor_weakness_needs_evidence():
    claim = "Strapi does not support visual page editing, so marketers wait on developers."
    assert "[competitor_claim]" in _flagged(_check("comparison", claim))
    assert _check("comparison", claim, searched=[STRAPI_DOCS])["passed"]


def test_advice_to_the_reader_is_not_a_competitor_claim():
    body = "With Strapi you don't need a separate admin panel for simple sites."
    assert _check("comparison", body)["passed"]


# ── best tools ───────────────────────────────────────────────────────────────


def test_best_tools_flags_absolute_ranking_but_not_fit_based_ranking():
    assert "[absolute_superlative]" in _flagged(
        _check("best-tools", "Nextly leads the market for headless content.")
    )
    assert _check("best-tools", "Nextly is the best pick for TypeScript teams.")["passed"]


def test_best_tools_superlative_stands_when_a_source_states_it():
    body = "WordPress is the most popular CMS, used by 43.2% of all websites."
    assert "[absolute_superlative]" in _flagged(_check("best-tools", body))
    result = _check("best-tools", body, searched=[W3TECHS], products=[{"name": "WordPress"}])
    assert result["passed"], result["detail"]


def test_entity_names_are_read_from_every_commercial_outline_shape():
    outline = {
        "products": [{"name": "Contentful"}],
        "ranked_tools": [{"name": "Sanity", "rank": 1}],
        "alternatives_list": {"competitors": [{"competitor_name": "Storyblok"}]},
        "roundup": {"products": ["Payload"]},
        "brand_voice_promotion": {"brand_name": "Nextly"},
        "sections": [{"heading": "Why teams switch", "name": "why teams switch"}],
    }
    assert set(outline_entity_names(outline, "Nextly")) == {
        "Contentful",
        "Sanity",
        "Storyblok",
        "Payload",
    }


# ── blog ─────────────────────────────────────────────────────────────────────


def test_blog_flags_invented_testing_and_unprofiled_experience():
    body = "We tested five headless CMSs over two weeks.\nIn my 12 years as a developer, schemas mattered most."
    detail = _flagged(_check("blog", body, author_profile=AUTHOR_PROFILE))
    assert "tested" in detail and "12 years" in detail


def test_blog_keeps_experience_the_author_profile_states_and_plain_opinion():
    body = (
        "I've spent 8 years building headless sites, and schema design is where projects go wrong.\n"
        "In my experience, editors care more about previews than APIs.\n"
        "The fastest way to start is the official CLI.\n"
        "Follow these 3 steps before you migrate in 2026."
    )
    result = _check("blog", body, author_profile=AUTHOR_PROFILE)
    assert result["passed"], result["detail"]


# ── buying guide ─────────────────────────────────────────────────────────────


def test_buying_guide_price_must_be_sourced_but_pricing_model_is_fine():
    assert "[pricing]" in _flagged(
        _check("buying-guide", "Expect to pay $99 per month for Contentful's entry plan.")
    )
    assert _check("buying-guide", "Contentful offers a free plan and paid tiers.")["passed"]


# ── product / service pages ──────────────────────────────────────────────────


def test_product_homepage_flags_unapproved_integrations_but_keeps_approved_stack():
    detail = _flagged(
        _check("product-homepage", "Nextly integrates with Shopify and Salesforce out of the box.")
    )
    assert "[brand_capability]" in detail and "Shopify" in detail
    assert _check("product-homepage", "Nextly is built on Next.js for TypeScript teams.")["passed"]


def test_service_page_flags_invented_client_tally_and_price():
    body = "We've helped 500 clients launch faster.\nOur migration package costs $2,500 per month."
    detail = _flagged(_check("service-page", body))
    assert "[fabricated_experience]" in detail or "[statistic]" in detail
    assert "[pricing]" in detail


# ── case study ───────────────────────────────────────────────────────────────


def test_case_study_result_must_match_brand_or_source_figures():
    assert _check(
        "case-study", "After switching, the team cut publishing time by 45% with Nextly."
    )["passed"]
    assert "[statistic]" in _flagged(
        _check("case-study", "After switching, the team cut publishing time by 70% with Nextly.")
    )


def test_case_study_flags_invented_client_outcome():
    body = "One of our ecommerce clients saw conversions jump after the move."
    assert "[fabricated_experience]" in _flagged(_check("case-study", body))


# ── white paper ──────────────────────────────────────────────────────────────


def test_white_paper_statistic_is_held_to_the_source_it_cites():
    cited = (
        "[73% of enterprises](https://example-research.org/headless-cms-report) plan to adopt "
        "a headless CMS within two years."
    )
    assert _check("white-paper", cited, searched=[SURVEY])["passed"]

    miscited = (
        "[73% of enterprises](https://www.contentful.com/pricing/) plan to adopt a headless CMS "
        "within two years."
    )
    assert "[statistic]" in _flagged(
        _check("white-paper", miscited, searched=[SURVEY, CONTENTFUL_PRICING])
    )


# ── glossary ─────────────────────────────────────────────────────────────────


def test_glossary_definition_cannot_carry_an_invented_statistic():
    body = "A headless CMS separates content from presentation and cuts page load time by 50%."
    assert "[statistic]" in _flagged(_check("glossary", body))
    assert _check("glossary", "A headless CMS separates content from presentation.")["passed"]


# ── tutorial / how-to ────────────────────────────────────────────────────────


@pytest.mark.parametrize("content_type", ["tutorial", "how-to-guide"])
def test_tutorial_version_requirement_must_be_verified(content_type):
    body = "Install Node.js version 18.18 or later before running the installer."
    assert "[version_or_date]" in _flagged(_check(content_type, body))
    assert _check(content_type, body, searched=[NODE_DOCS])["passed"]


# ── landing / sales pages ────────────────────────────────────────────────────


@pytest.mark.parametrize("content_type", ["landing-page", "sales-page"])
def test_landing_and_sales_pages_keep_promotion_without_invented_proof(content_type):
    detail = _flagged(
        _check(content_type, "Trusted by 10,000+ developers, Nextly is the #1 headless CMS.")
    )
    assert "[statistic]" in detail and "[absolute_superlative]" in detail

    promotion = (
        "Nextly gives TypeScript teams a visual page builder on top of a headless CMS.\n"
        "Teams using Nextly cut publishing time by 45%."
    )
    assert _check(content_type, promotion)["passed"]


# ── no evidence at all ───────────────────────────────────────────────────────


def test_without_captured_evidence_specifics_are_treated_as_unverified():
    spec = build_requirements_spec({}, "blog", "headless cms", "Headless CMS Guide")
    result = check_unsupported_claims(_article("Headless CMS adoption grew 300% last year."), spec)
    assert "[statistic]" in _flagged(result)


def test_meta_description_is_checked_too():
    article = _article("Clean body.")
    article["meta_description"] = "Strapi Cloud costs $29/month — compare headless cms plans."
    assert "[pricing]" in _flagged(check_unsupported_claims(article, _spec("comparison")))


def test_detail_tells_repair_to_soften_not_substitute():
    detail = _flagged(_check("comparison", "Strapi Cloud costs $29/month for the Pro tier."))
    assert "Strapi Cloud costs $29/month" in detail
    assert "never substitute another figure" in detail
    assert "do not add a generic disclaimer" in detail


def test_headings_are_not_graded_as_verdicts():
    assert _check("best-tools", "## Why Nextly Is the Best Choice\n\nPick by fit.")["passed"]


# ── repair plumbing ──────────────────────────────────────────────────────────


def test_repair_prompt_receives_sources_and_approved_brand_facts():
    failed = [{"name": "unsupported_claims", "detail": "..."}]
    sources = _build_sources_block(failed, [CONTENTFUL_PRICING])
    assert CONTENTFUL_PRICING["url"] in sources

    brand_block = _build_brand_block(failed, BRAND, "comparison")
    assert "Nextly" in brand_block and "https://nextlyhq.com" in brand_block
    assert "cut publishing time by 45%" in brand_block


@pytest.mark.asyncio
async def test_final_validation_repairs_claims_introduced_by_humanization():
    humanized = _article(
        "## How Nextly differs\n\nNextly is the best fit for TypeScript teams. "
        "Strapi Cloud costs $29/month for the Pro tier."
    )

    def _soften_price(*, final_content, **_kwargs):
        # Mirrors a surgical repair: only the flagged sentence changes.
        body = final_content["body_markdown"].replace(
            "Strapi Cloud costs $29/month for the Pro tier.",
            "Strapi Cloud offers a free tier and paid plans.",
        )
        return {**final_content, "body_markdown": body}

    state = {
        "content": {
            "content_type": "comparison",
            "selected_topic": "Nextly vs Contentful vs Strapi",
            "focus_keyword": "headless cms",
            "outline": _outline("comparison"),
            "final_content": humanized,
            "generation_meta": {"searched_results": [CONTENTFUL_PRICING], "author_profile": ""},
            "review": {},
        }
    }
    repair = AsyncMock(side_effect=_soften_price)
    with (
        patch.object(validation, "run_targeted_repair", repair),
        patch.object(
            validation,
            "enforce_subheadings_for_spec",
            AsyncMock(side_effect=lambda c, *_a, **_k: c),
        ),
    ):
        result = await validation.final_validate_content(state)

    kwargs = repair.await_args.kwargs
    assert "unsupported_claims" in [c["name"] for c in kwargs["failed_checks"]]
    assert kwargs["searched_results"] == [CONTENTFUL_PRICING]
    shipped = result["content"]["final_content"]["body_markdown"]
    assert "$29" not in shipped
    assert "Strapi Cloud offers a free tier and paid plans." in shipped
    assert "Nextly is the best fit for TypeScript teams." in shipped  # promotion kept
    final_failed = [
        c["name"] for c in result["content"]["review"]["final_validation"]["failed_checks"]
    ]
    assert "unsupported_claims" not in final_failed


@pytest.mark.asyncio
async def test_validate_content_blocks_unsupported_claims_so_repair_runs():
    state = {
        "content": {
            "content_type": "blog",
            "selected_topic": "Headless CMS Guide",
            "outline": {"title": "Headless CMS Guide"},
            "final_content": _article(
                "We benchmarked six CMSs and Payload was 3x faster than the rest."
            ),
            "generation_meta": {"searched_results": [], "author_profile": AUTHOR_PROFILE},
            "review": {},
        }
    }
    result = await validation.validate_content(state)
    failed = result["content"]["review"]["validation"]["failed_checks"]
    assert "unsupported_claims" in [c["name"] for c in failed]


# ── prompts: the sources of invention are gone ──────────────────────────────


def test_writer_prompt_no_longer_demands_invented_experience():
    middleware = PersonaInjectionMiddleware(counters={})
    prompt = middleware._build_full_content_prompt(None, {"title": "t"}, 1500, "comparison")
    assert "FACTUAL INTEGRITY" in prompt
    for invented_example in (
        "I've spent 11 years",
        "organic reach tripled",
        "After reviewing 200+",
        "write a first-person persona anecdote instead",
        "don't need sourcing",
    ):
        assert invented_example not in prompt


def test_humanizer_is_told_not_to_add_facts():
    assert "FACTUAL INTEGRITY" in HUMANIZE_SYSTEM_PROMPT
    assert "Add 1–2 real-feeling examples" not in HUMANIZE_SYSTEM_PROMPT


# --- hedged and framing sentences aren't claims (G54, rext-control#491) ----------------


@pytest.mark.parametrize(
    "text",
    [
        # The staging article's sentence (f82b2431), followed by a first-person one.
        "Each tool got a score out of ten. Treat these scores as directional, not "
        "'lab-tested.' Our picks lean toward agencies that publish weekly.",
        "We haven't tested every plan ourselves, so read these prices as a guide.",
        "We have not personally benchmarked these tools; treat the ratings as a starting point.",
        "The marketing copy was explicit. (It said \u201clab-tested.\u201d) Our picks favor agencies.",
    ],
)
def test_a_hedged_or_framing_sentence_is_not_a_testing_claim(text):
    assert [c.category for c in find_unsupported_claims(text, {})] == []


@pytest.mark.parametrize(
    ("text", "span"),
    [
        ("We tested all five tools for a month before ranking them.", "tested"),
        ("Our team benchmarked each tool on real client sites.", "benchmarked"),
        ("There's no doubt we tested every tool on this list.", "tested"),
        ("We haven't tested every product, but we tested the top five ourselves.", "tested"),
        ("We never guessed; we tested every tool for a month.", "tested"),
        ("Without hesitation, we tested every tool for a month.", "tested"),
        ("We never rank products without hands-on testing.", "hands-on testing"),
        # A graded denial still says some testing was done.
        ("We have not fully tested every integration.", "tested"),
        ("We haven't properly tested the enterprise tier.", "tested"),
        ("We have not formally benchmarked the free plan.", "benchmarked"),
        ("We haven't officially tested the API yet.", "tested"),
    ],
)
def test_a_real_testing_claim_is_still_caught(text, span):
    claims = find_unsupported_claims(text, {})
    assert [(c.category, c.span) for c in claims] == [("fabricated_experience", span)]


@pytest.mark.parametrize(
    "text",
    [
        "\u201c73% of enterprises plan to adopt a headless CMS.\u201d [Report](https://example.com/r)",
        "73% of enterprises plan to adopt a headless CMS. [Report](https://example.com/r)",
        "73% of enterprises plan to adopt a headless CMS. [Report](https://example.com/r).",
    ],
)
def test_a_trailing_citation_stays_with_its_sentence(text):
    # Split off, the claim lost its source and was weighed against every source instead.
    units = claim_integrity._units(text)
    assert [u.cited_urls for u in units] == [("https://example.com/r",)]
    assert "73% of enterprises" in units[0].text


@pytest.mark.parametrize(
    "citations",
    [
        "[Report A](https://example.com/a) and [Report B](https://example.com/b)",
        "[Report A](https://example.com/a), [Report B](https://example.com/b)",
        "[Report A](https://example.com/a) & [Report B](https://example.com/b).",
        "[Report A](https://example.com/a), and [Report B](https://example.com/b)",
    ],
)
def test_several_trailing_citations_stay_with_their_sentence(citations):
    # Joined by "and", the pair read as a sentence of its own and the claim had no source.
    text = f"\u201c73% of enterprises plan to adopt a headless CMS.\u201d {citations}"
    units = claim_integrity._units(text)
    assert [u.cited_urls for u in units] == [("https://example.com/a", "https://example.com/b")]
    assert "73% of enterprises" in units[0].text


def test_linked_names_that_open_a_sentence_are_not_a_citation():
    text = "We compared plans. [Ahrefs](https://ahrefs.com/x) and [Moz](https://moz.com/y) agree."
    units = claim_integrity._units(text)
    assert [(u.text, u.cited_urls) for u in units] == [
        ("We compared plans.", ()),
        ("Ahrefs and Moz agree.", ("https://ahrefs.com/x", "https://moz.com/y")),
    ]


def test_a_sentence_that_starts_with_a_link_is_its_own():
    text = "We compared plans. [Ahrefs](https://ahrefs.com/x) found 73% use one tool."
    units = claim_integrity._units(text)
    assert [(u.text, u.cited_urls) for u in units] == [
        ("We compared plans.", ()),
        ("Ahrefs found 73% use one tool.", ("https://ahrefs.com/x",)),
    ]


def test_a_sentence_ends_after_a_closing_quote():
    text = "Call it 'good enough.' We tested it. He said “done.” Then we left."
    assert [u.text for u in claim_integrity._units(text)] == [
        "Call it 'good enough.'",
        "We tested it.",
        "He said “done.”",
        "Then we left.",
    ]
