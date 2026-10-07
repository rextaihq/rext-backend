"""The brand-mention choice at the outline gate is followed exactly (rext-control#700).

"None" used only to skip the promotion blocks: nothing told the writer to keep the brand out, every
brand check skipped, and an outline generated before the choice could already name the brand, so a
mention could ship. "Subtle" keeps the brand out of a call to action, which an outline's call to
action naming the brand contradicted.
"""

import json
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

import src.flow.engines.content.generation.content_generation as node
from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
from src.flow.engines.content.generation.humanize_content import _build_prompt_data
from src.flow.engines.content.generation.requirements_spec import (
    brand_kept_out_of_cta,
    brand_named_in,
    build_requirements_spec,
    excluded_brand_of,
)
from src.flow.engines.content.generation.validation import check_brand_absent

BRAND = {"brand_name": "Acme Tools", "brand_url": "https://www.acme.test/"}
ARTICLE = {
    "title": "How to plan a vegetable garden",
    "meta_title": "How to plan a vegetable garden",
    "meta_description": "A plan for a vegetable garden.",
    "introduction": "Plan a vegetable garden before you dig.",
    "body_markdown": "## Choose the spot\n\nSun matters most.",
    "cta": {"text": "Start planning your garden today"},
}


def _outline(prominence, **extra):
    return {
        "title": ARTICLE["title"],
        "brand_prominence": prominence,
        "promote_brand": prominence in ("prominent", "subtle"),
        "brand_voice_promotion": dict(BRAND),
        **extra,
    }


# -- Which brand stays out ------------------------------------------------------------


def test_none_keeps_the_brand_out_and_the_others_do_not():
    assert excluded_brand_of(_outline("none")) == {
        "brand_name": "Acme Tools",
        "brand_url": "https://www.acme.test/",
    }
    assert excluded_brand_of(_outline("subtle")) is None
    assert excluded_brand_of(_outline("prominent")) is None
    assert excluded_brand_of({"brand_prominence": "none"}) is None  # no brand known


def test_none_and_subtle_keep_the_brand_out_of_the_call_to_action():
    assert brand_kept_out_of_cta(_outline("none")) == "Acme Tools"
    assert brand_kept_out_of_cta(_outline("subtle")) == "Acme Tools"
    assert brand_kept_out_of_cta(_outline("prominent")) == ""


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("Try Acme Tools free", True),
        ("try acme tools today", True),
        ("Acme Toolshed is different", False),
        ("Plan your garden", False),
    ],
)
def test_a_brand_is_named_as_a_word_of_its_own(text, named):
    assert brand_named_in(text, "Acme Tools") is named


def test_the_spec_carries_the_excluded_brand_only_for_none():
    assert build_requirements_spec(_outline("none"), "blog")["excluded_brand"]["brand_name"] == (
        "Acme Tools"
    )
    assert build_requirements_spec(_outline("subtle"), "blog")["excluded_brand"] is None


# -- The check -------------------------------------------------------------------------


def _absent(article, prominence="none"):
    return check_brand_absent(article, build_requirements_spec(_outline(prominence), "blog"))


def test_an_article_without_the_brand_passes():
    assert _absent(ARTICLE)["passed"] is True


@pytest.mark.parametrize(
    ("field", "value", "place"),
    [
        ("title", "Acme Tools: how to plan a garden", "title"),
        ("meta_description", "Plan a garden with Acme Tools.", "meta description"),
        ("introduction", "acme tools makes this easy.", "introduction"),
        ("body_markdown", "## Tools\n\nWe use [a planner](https://acme.test/planner).", "body"),
        ("cta", {"text": "Try Acme Tools free"}, "call to action"),
    ],
)
def test_a_mention_anywhere_blocks_under_none(field, value, place):
    result = _absent({**ARTICLE, field: value})

    assert result["passed"] is False and result["severity"] == "blocking"
    assert place in result["detail"] and "Acme Tools" in result["detail"]


def test_with_a_mention_approved_the_check_does_not_apply():
    article = {**ARTICLE, "body_markdown": "Acme Tools helps here."}
    assert _absent(article, "subtle")["passed"] is True
    assert _absent(article, "prominent")["passed"] is True


# -- What the writer, the system prompt and the rewrite are told -----------------------


class _Writer:
    """The content agent: records the messages it was given, then returns the article."""

    def __init__(self, seen):
        self.seen = seen

    async def astream_events(self, payload, *_args, **_kwargs):
        self.seen.extend(payload["messages"])
        yield {
            "event": "on_chain_end",
            "name": "agent",
            "run_id": "root",
            "data": {"output": {"messages": [AIMessage(content=json.dumps(ARTICLE))]}},
        }


@pytest.fixture
def writer_message(monkeypatch):
    """The human message generate_content gives the writer, for a given outline."""

    async def consume(*_args, **_kwargs):
        return None

    monkeypatch.setattr(node, "consume_stage_credits", consume)
    monkeypatch.setattr(node, "_fetch_known_entities", AsyncMock(return_value=(None, [])))
    monkeypatch.setattr(node, "research_official_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        node,
        "enforce_subheadings_for_spec",
        AsyncMock(side_effect=lambda content, *a, **k: content),
    )
    monkeypatch.setattr(node, "get_stream_writer", lambda: lambda _event: None)
    monkeypatch.setattr(node, "can_afford_stage", AsyncMock(return_value=False))

    async def go(outline):
        seen = []

        async def create_content_agent(**_kwargs):
            return _Writer(seen)

        monkeypatch.setattr(node, "create_content_agent", create_content_agent)
        await node.generate_content(
            {
                "content": {
                    "selected_topic": ARTICLE["title"],
                    "content_type": "blog",
                    "outline": outline,
                },
                "serp_payload": {"user_id": "u", "workspace_id": "w", "keyword": "garden"},
            }
        )
        return "\n".join(str(m.content) for m in seen)

    return go


@pytest.mark.asyncio
async def test_under_none_the_writer_is_told_to_keep_the_brand_out(writer_message):
    message = await writer_message(_outline("none"))

    assert "BRAND EXCLUSION — REQUIRED" in message
    assert "The user chose NO mention of Acme Tools" in message
    assert "FINAL CHECK BEFORE YOU WRITE: Acme Tools appears nowhere" in message
    assert "PRODUCT-LED MENTION" not in message


@pytest.mark.asyncio
@pytest.mark.parametrize("prominence", ["none", "subtle"])
async def test_a_call_to_action_naming_the_brand_is_rewritten_without_it(
    writer_message, prominence
):
    outline = _outline(prominence, final_cta={"primary_cta": "Get started with Acme Tools"})

    message = await writer_message(outline)

    assert "It names Acme Tools, but the user's choice keeps Acme Tools out" in message
    assert "WITHOUT naming Acme Tools" in message
    assert "using this exact CTA text" not in message


@pytest.mark.asyncio
async def test_a_prominent_call_to_action_keeps_its_exact_text(writer_message):
    outline = _outline("prominent", final_cta={"primary_cta": "Get started with Acme Tools"})

    message = await writer_message(outline)

    assert "using this exact CTA text" in message
    assert "BRAND EXCLUSION" not in message


def test_the_system_prompt_states_the_exclusion():
    outline = _outline("none")
    block = PersonaInjectionMiddleware()._build_brand_placement_block(
        outline, "blog", excluded_brand_of(outline)
    )

    assert block.startswith("## BRAND EXCLUSION — MANDATORY")
    assert "NO mention of Acme Tools" in block
    # The human message keeps the approved internal links; the system prompt says so too.
    assert "the approved internal links you are given stay" in block
    # The caller decides from the run's own title and keyphrase; with none excluded, no block.
    assert PersonaInjectionMiddleware()._build_brand_placement_block(outline, "blog", None) == ""


def test_the_rewrite_is_told_to_keep_the_brand_out():
    data = _build_prompt_data(
        content_payload=dict(ARTICLE),
        content_type="blog",
        excluded_brand=excluded_brand_of(_outline("none")),
    )

    assert data["brand_instruction"].startswith("BRAND EXCLUSION")
    assert "Acme Tools" in data["brand_instruction"]


# -- Review round 1 of #918 ---------------------------------------------------------------


def test_a_call_to_action_linking_to_the_brand_blocks_under_none():
    article = {**ARTICLE, "cta": {"text": "Get started", "url": "https://acme.test/signup"}}

    result = _absent(article)

    assert result["passed"] is False and "call to action's link" in result["detail"]


def test_approved_internal_links_are_not_brand_links():
    """The workspace's own approved pages share the brand's host; the user chose to keep them."""
    internal = "https://www.acme.test/blog/garden-planner"
    outline = _outline("none", internal_links=[{"url": internal, "title": "Garden planner"}])
    article = {**ARTICLE, "body_markdown": f"See [our planner]({internal}) first."}

    assert check_brand_absent(article, build_requirements_spec(outline, "blog"))["passed"] is True
    other = {**ARTICLE, "body_markdown": "See [the shop](https://acme.test/shop)."}
    assert check_brand_absent(other, build_requirements_spec(outline, "blog"))["passed"] is False


@pytest.mark.parametrize(
    "outline_extra",
    [
        {"title": "Acme Tools login: a step-by-step guide"},
        {"focus_keyphrase": "acme tools login"},
    ],
)
def test_none_cannot_exclude_a_brand_the_title_or_keyphrase_names(outline_extra):
    """The title stays verbatim and the keyphrase must appear: None means no promotion there."""
    assert excluded_brand_of(_outline("none", **outline_extra)) is None


@pytest.mark.parametrize(
    ("text", "counts"),
    [
        ("Save this for later.", False),
        ("Later you can review it.", False),  # sentence start: ordinary use
        ("Later, the team reviews it.", False),
        ("We scheduled it in Later last week.", True),
        ("## Later\n\nIt helps.", False),  # a heading's first word, alone
        ("Later is a social media scheduler.", True),  # a sentence start used as a name
        ("Later can help you plan the week.", True),
    ],
)
def test_a_one_word_brand_that_is_an_ordinary_word_counts_only_as_the_name(text, counts):
    outline = {
        "title": "How to schedule posts",
        "brand_prominence": "none",
        "brand_voice_promotion": {"brand_name": "Later", "brand_url": ""},
    }
    article = {**ARTICLE, "title": "How to schedule posts", "body_markdown": text}

    result = check_brand_absent(article, build_requirements_spec(outline, "blog"))

    assert result["passed"] is (not counts)


def test_a_subtle_call_to_action_must_not_link_to_the_brand():
    from src.flow.engines.content.generation.validation import check_brand_prominence

    article = {
        **ARTICLE,
        "body_markdown": "## Choose the spot\n\nAcme Tools maps the sun for you.",
        "cta": {"text": "Get started", "url": "https://acme.test"},
    }

    result = check_brand_prominence(article, build_requirements_spec(_outline("subtle"), "blog"))

    assert result["passed"] is False and "must not send readers" in result["detail"]


@pytest.mark.asyncio
async def test_humanize_bringing_the_brand_back_is_repaired_after_it(monkeypatch):
    """With no brand context (None), the final pass still routes brand_absent to repair."""
    import src.flow.engines.content.generation.validation as validation

    asked = []

    async def repair(**kwargs):
        asked.extend(c["name"] for c in kwargs["failed_checks"])
        return None

    monkeypatch.setattr(validation, "run_targeted_repair", repair)
    monkeypatch.setattr(
        validation,
        "enforce_subheadings_for_spec",
        AsyncMock(side_effect=lambda content, *a, **k: content),
    )
    article = {**ARTICLE, "body_markdown": "## Choose the spot\n\nAcme Tools maps the sun."}
    await validation.final_validate_content(
        {
            "content": {
                "final_content": article,
                "outline": _outline("none"),
                "content_type": "blog",
                "selected_topic": ARTICLE["title"],
            },
            "serp_payload": {"keyword": "vegetable garden"},
        }
    )

    assert "brand_absent" in asked


# -- Review round 2 of #918 ---------------------------------------------------------------


def test_a_subdomain_of_the_brand_is_its_site():
    article = {**ARTICLE, "body_markdown": "Sign up at [the app](https://app.acme.test/signup)."}

    assert _absent(article)["passed"] is False


def test_a_subtle_call_to_action_rendered_as_a_brand_link_is_caught():
    from src.flow.engines.content.generation.validation import check_brand_prominence

    article = {
        **ARTICLE,
        "body_markdown": "Acme Tools maps the sun.\n\n[Get started](https://shop.acme.test)",
        "cta": {"text": "Get started"},
    }

    result = check_brand_prominence(article, build_requirements_spec(_outline("subtle"), "blog"))

    assert result["passed"] is False and "https://shop.acme.test" in result["detail"]


def test_the_runs_own_keyphrase_decides_not_a_stale_outline_copy():
    """A resumed run: the outline has no keyphrase, the run's is "acme tools login"."""
    spec = build_requirements_spec(_outline("none"), "blog", focus_keyword="acme tools login")

    assert spec["excluded_brand"] is None


@pytest.mark.parametrize("prominence", ["none", "subtle"])
def test_a_malformed_address_is_no_brand_link_and_never_stops_the_check(prominence):
    from src.flow.engines.content.generation.validation import check_brand_prominence

    article = {
        **ARTICLE,
        "body_markdown": "## Choose the spot\n\nSee https://[bad for the chart.",
        "cta": {"text": "Get started", "url": "https://[bad"},
    }
    spec = build_requirements_spec(_outline(prominence), "blog")

    assert check_brand_absent(article, spec)["passed"] is True
    assert isinstance(check_brand_prominence(article, spec)["passed"], bool)


# -- The conflicts a repair couldn't resolve (rext-control#760) ---------------------------


def _checked(article, outline, generation_meta=None):
    """The article as a validation pass sees it, and the spec it is checked against."""
    from src.flow.engines.content.generation.validation import restore_links_for_spec

    spec = build_requirements_spec(outline, "blog", generation_meta=generation_meta)
    return restore_links_for_spec(article, spec, stage="test"), spec


def test_links_to_the_excluded_brands_site_are_removed_in_code():
    article = {
        **ARTICLE,
        "body_markdown": (
            "## Choose the spot\n\nSee [the sun chart](https://app.acme.test/chart) and "
            "[a soil guide](https://soil.example/guide). ![chart](https://acme.test/chart.png)"
        ),
        "cta": {"text": "Start planning your garden today", "url": "https://acme.test/signup"},
    }

    cleaned, spec = _checked(article, _outline("none"))

    # The words stay, the address goes; another site's link and an image are left alone.
    assert (
        "See the sun chart and [a soil guide](https://soil.example/guide)."
        in (cleaned["body_markdown"])
    )
    assert "![chart](https://acme.test/chart.png)" in cleaned["body_markdown"]
    assert cleaned["cta"] == {"text": "Start planning your garden today", "url": None}
    # What is left passes the check: an image stored on the brand's domain is no link to its
    # site (a staging run failed "no mention" on the article's own generated image).
    assert check_brand_absent(cleaned, spec)["passed"] is True
    assert article["cta"]["url"] == "https://acme.test/signup"  # the input isn't changed


def test_an_approved_internal_link_on_the_brands_site_stays_linked():
    internal = "https://www.acme.test/blog/garden-planner"
    outline = _outline("none", internal_links=[{"url": internal, "title": "Garden planner"}])
    article = {**ARTICLE, "body_markdown": f"See [our planner]({internal}) first."}

    cleaned, _ = _checked(article, outline)

    assert cleaned is article


@pytest.mark.parametrize("prominence", ["prominent", "subtle"])
def test_with_a_mention_approved_no_link_is_removed(prominence):
    article = {**ARTICLE, "body_markdown": "Try [Acme Tools](https://acme.test) for the map."}

    cleaned, _ = _checked(article, _outline(prominence))

    assert cleaned is article


def test_a_citation_to_the_excluded_brands_site_is_not_kept_or_put_back():
    from src.flow.engines.content.generation.validation import (
        check_links_preserved,
        protected_links,
    )

    brand_page = "https://acme.test/blog/soil"
    record = {
        "url": brand_page,
        "anchor_text": "a soil study",
        "sentence": "A soil study shows why.",
        "section": "Choose the spot",
        "field": "body_markdown",
        "kind": "citation",
    }
    searched = [{"url": brand_page, "title": "Soil"}]
    article = {**ARTICLE, "body_markdown": "## Choose the spot\n\nA soil study shows why."}

    cleaned, spec = _checked(article, _outline("none"), {"link_inventory": [record]})

    # Not in the inventory, so it is not put back and "a link was lost" has nothing to report.
    assert spec["link_inventory"] == []
    assert "acme.test" not in cleaned["body_markdown"]
    assert check_links_preserved(cleaned, spec)["passed"] is True
    # And a draft that still links it does not get that link protected.
    linked = {**ARTICLE, "body_markdown": f"## Choose the spot\n\n[A soil study]({brand_page})."}
    assert protected_links(linked, spec, searched) == []
    # With a mention approved the same citation is kept, as before.
    kept = build_requirements_spec(
        _outline("subtle"), "blog", generation_meta={"link_inventory": [record]}
    )
    assert [r["url"] for r in kept["link_inventory"]] == [brand_page]


def test_a_planned_heading_that_names_the_brand_is_met_without_the_name():
    from src.flow.engines.content.generation.validation import check_required_sections

    spec = build_requirements_spec(_outline("none"), "blog")
    spec["planned_sections"] = [
        {
            "heading": "Acme Tools pricing",
            "level": 2,
            "position": 1,
            "of": 2,
            "required": True,
            "plan": "",
        },
        # The brand's own entry in a list: another product is named there, or none.
        {"heading": "Acme Tools", "level": 2, "position": 2, "of": 2, "required": True, "plan": ""},
    ]
    article = {**ARTICLE, "body_markdown": "## Pricing\n\nPlans start small."}

    assert check_required_sections(article, spec)["passed"] is True
    assert check_brand_absent(article, spec)["passed"] is True
    # With a mention approved the name is part of what the heading must say.
    named = build_requirements_spec(_outline("subtle"), "blog")
    named["planned_sections"] = spec["planned_sections"][:1]
    assert check_required_sections(article, named)["passed"] is False
    # With the heading missing altogether, the repair is told to write it without the name.
    missing = check_required_sections({**ARTICLE, "body_markdown": "## Soil\n\nDig."}, spec)
    assert missing["passed"] is False
    assert "write its heading without that name" in missing["detail"]


def test_a_hero_that_names_the_brand_is_met_without_the_name():
    from src.flow.engines.content.generation.validation import check_hero_presence

    hero = {"headline": "Acme Tools for gardens", "subheadline": ""}
    article = {**ARTICLE, "introduction": "Plan your gardens before you dig, bed by bed."}

    spec = build_requirements_spec(_outline("none", hero=hero), "blog")
    assert check_hero_presence(article, spec)["passed"] is True
    # With a mention approved the name is part of the hero the opening must carry.
    named = build_requirements_spec(_outline("subtle", hero=hero), "blog")
    assert check_hero_presence(article, named)["passed"] is False


def test_the_repair_is_told_about_the_exclusion_and_shown_the_call_to_action():
    from src.flow.engines.content.generation.repair_content import _build_exclusion_block

    failed = [{"name": "brand_absent", "detail": "…"}]
    article = {**ARTICLE, "cta": {"text": "Try Acme Tools today"}}

    block = _build_exclusion_block(failed, dict(BRAND), article)

    assert block.startswith("BRAND EXCLUSION — the user chose NO mention of Acme Tools.")
    assert 'The call to action reads "Try Acme Tools today".' in block
    assert "return `cta.text` reworded without it" in block
    # Only when that check failed, and only for an excluded brand.
    assert _build_exclusion_block([{"name": "cta_presence"}], dict(BRAND), article) == ""
    assert _build_exclusion_block(failed, None, article) == ""


def test_a_persona_named_like_the_excluded_brand_is_recognised():
    from types import SimpleNamespace

    from src.flow.engines.agent.middleware.persona_middleware import _is_named

    assert _is_named(SimpleNamespace(full_name="Acme  Tools", name="acme"), "acme tools")
    assert _is_named(SimpleNamespace(full_name=None, name="ACME TOOLS"), "Acme Tools")
    assert not _is_named(SimpleNamespace(full_name="Sara Ortiz", name="sara"), "Acme Tools")
    assert not _is_named(SimpleNamespace(full_name=None, name=None), "")


def test_tags_and_alt_text_that_name_the_excluded_brand_are_cleaned_in_code():
    article = {
        **ARTICLE,
        "tags": ["Gardening", "Acme Tools", "acme tools tips"],
        "images": [
            {"image_url": "https://cdn.example/a.png", "alt_text": "Acme Tools' sun chart"},
            {"image_url": "https://cdn.example/b.png", "alt_text": "A raised bed"},
        ],
    }

    cleaned, _ = _checked(article, _outline("none"))

    assert cleaned["tags"] == ["Gardening"]
    assert [image["alt_text"] for image in cleaned["images"]] == ["sun chart", "A raised bed"]
    # With a mention approved, both stay as written.
    kept, _ = _checked(article, _outline("prominent"))
    assert kept is article


# -- Review round 1 of #938 ---------------------------------------------------------------

LATER = {"brand_name": "Later", "brand_url": "https://later.test/"}


def _later_outline(**extra):
    return {**_outline("none"), "brand_voice_promotion": dict(LATER), **extra}


def test_a_one_word_brand_is_taken_out_only_where_it_is_the_name():
    from src.flow.engines.content.generation.validation import check_required_sections

    article = {
        **ARTICLE,
        "body_markdown": "## What to do afterwards\n\nWater the beds.",
        "tags": ["Later", "See you later", "Gardening"],
        "images": [
            {
                "image_url": "https://cdn.example/a.png",
                "alt_text": "Return later to water the plants",
            },
            {"image_url": "https://cdn.example/b.png", "alt_text": "The Later dashboard"},
        ],
    }

    cleaned, spec = _checked(article, _later_outline())

    # The tag that is the name goes; the ordinary word in a tag and in an alt text stays.
    assert cleaned["tags"] == ["See you later", "Gardening"]
    assert [image["alt_text"] for image in cleaned["images"]] == [
        "Return later to water the plants",
        "The dashboard",
    ]
    # A planned heading with the ordinary word is still asked for as written.
    spec["planned_sections"] = [
        {
            "heading": "What to do later",
            "level": 2,
            "position": 1,
            "of": 1,
            "required": True,
            "plan": "",
        }
    ]
    assert check_required_sections(cleaned, spec)["passed"] is False


def test_the_link_lists_lose_the_entry_of_a_link_removed_in_code():
    brand_page = "https://acme.test/blog/soil"
    article = {
        **ARTICLE,
        "body_markdown": f"## Choose the spot\n\n[A soil study]({brand_page}) and [a guide](https://soil.example/g).",
        "outbound_links": [
            {"url": brand_page, "anchor_text": "A soil study"},
            {"url": "https://soil.example/g", "anchor_text": "a guide"},
        ],
    }

    cleaned, _ = _checked(article, _outline("none"))

    assert "acme.test" not in cleaned["body_markdown"]
    assert [entry["url"] for entry in cleaned["outbound_links"]] == ["https://soil.example/g"]


def test_an_approved_page_linked_with_a_fragment_is_still_approved():
    internal = "https://www.acme.test/blog/garden-planner"
    outline = _outline("none", internal_links=[{"url": internal, "title": "Garden planner"}])
    article = {
        **ARTICLE,
        "body_markdown": f"See [our planner]({internal}/#steps) and [it again]({internal}?utm_source=x).",
    }

    cleaned, spec = _checked(article, outline)

    assert cleaned is article
    assert check_brand_absent(cleaned, spec)["passed"] is True


def test_an_image_stored_on_the_brands_domain_is_not_a_link_to_its_site():
    article = {
        **ARTICLE,
        "body_markdown": "## Choose the spot\n\n![A sun chart](https://media.acme.test/generated/a.png)\n\nSun.",
    }
    spec = build_requirements_spec(_outline("none"), "blog")

    assert check_brand_absent(article, spec)["passed"] is True
    # A text link to the same host is still one.
    linked = {**article, "body_markdown": "See [the chart](https://media.acme.test/chart)."}
    assert check_brand_absent(linked, spec)["passed"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("prominence", ["none", "subtle"])
async def test_a_call_to_action_without_the_brand_links_to_no_one_else(writer_message, prominence):
    for text in ("Start planning today", "Get started with Acme Tools"):
        message = await writer_message(_outline(prominence, final_cta={"primary_cta": text}))

        assert "Leave the call to action's `url` empty (null)" in message
        assert "Do not link it to another company's product or site instead" in message


@pytest.mark.asyncio
async def test_a_prominent_call_to_action_may_link(writer_message):
    message = await writer_message(
        _outline("prominent", final_cta={"primary_cta": "Start planning today"})
    )

    assert "Leave the call to action's `url` empty" not in message
