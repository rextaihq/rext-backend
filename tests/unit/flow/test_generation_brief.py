"""One brief for one article, the same at every stage (FB2.21, revnix/rext-control#702, P1).

The writer and the rewrite each rebuilt their own sentences about the reader, the tone, the
length, the keywords and the brand choice. The brief states each once, read from the spec the
article is checked against.
"""

import pytest

from src.flow.engines.content.generation.generation_brief import (
    BRAND_CHOICE_LINES,
    build_generation_brief,
    render_generation_brief,
)
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec

FOCUS = "content calendar template"
TITLE = "How to use a content calendar template"
BRAND = {"brand_name": "Acme Tools", "brand_url": "https://www.acme.test/"}


def _outline(prominence=None, **extra):
    return {
        "title": TITLE,
        "focus_keyphrase": FOCUS,
        "keywords_to_include": [FOCUS, "editorial calendar", "posting schedule"],
        "target_audience": ["Marketing leads", " Small  agencies ", ""],
        "tone": "Practical,  plain-spoken",
        "target_word_count": 1500,
        "brand_prominence": prominence,
        "promote_brand": prominence in ("prominent", "subtle"),
        "brand_voice_promotion": dict(BRAND),
        "final_cta": {"primary_cta": "Start planning today"},
        **extra,
    }


def _brief(outline, content_type="blog"):
    spec = build_requirements_spec(outline, content_type, focus_keyword=FOCUS)
    return build_generation_brief(spec, outline), spec


def test_the_brief_holds_each_fact_once():
    brief, _ = _brief(_outline("subtle"))

    assert brief == {
        "title": TITLE,
        "content_type": "blog",
        "readers": ["Marketing leads", "Small agencies"],
        "tone": "Practical, plain-spoken",
        "target_words": 1500,
        "min_words": 1320,
        "max_words": 1680,
        "focus_keyphrase": FOCUS,
        "secondary_keywords": ["editorial calendar", "posting schedule"],
        "brand_choice": "subtle",
        "brand_name": "Acme Tools",
        "call_to_action": "Start planning today",
        "call_to_action_links": False,
        "call_to_action_without": "",
    }


def test_what_a_stage_is_told_is_what_the_article_is_checked_against():
    brief, spec = _brief(_outline("prominent"))

    assert brief["title"] == spec["selected_title"]
    assert brief["focus_keyphrase"] == spec["target_keyword"]
    assert brief["secondary_keywords"] == spec["secondary_keywords"]
    assert brief["target_words"] == spec["target_word_count"]
    assert brief["brand_name"] == spec["brand_context"]["brand_name"]


def test_the_wording_is_the_same_at_every_stage_but_for_the_stages_own_line():
    brief, _ = _brief(_outline("prominent"))
    writer, rewrite, repair = (
        render_generation_brief(brief, stage=stage).splitlines()
        for stage in ("writer", "rewrite", "repair")
    )

    assert writer[:3] == [
        "========================",
        "THE ARTICLE'S BRIEF",
        "========================",
    ]
    assert writer[3] == "Write the article this brief describes."
    assert rewrite[3].endswith("Rewrite its words; the brief stands.")
    assert repair[3].endswith("Fix the listed issues; the brief stands.")
    assert writer[4:] == rewrite[4:] == repair[4:]
    assert writer[4:] == [
        f'- Title (fixed, the user chose it): "{TITLE}"',
        "- Content type: blog",
        "- Written for: Marketing leads, Small agencies",
        "- Tone: Practical, plain-spoken",
        "- Length: about 1500 words; the introduction and the body together between 1320 and 1680",
        f'- Focus keyphrase (exact wording): "{FOCUS}"',
        "- Secondary keywords (each at least once): editorial calendar, posting schedule",
        f"- Brand: Acme Tools, prominent: {BRAND_CHOICE_LINES['prominent']}",
        '- Call to action: "Start planning today"',
    ]


@pytest.mark.parametrize(
    ("prominence", "brand_line", "call_to_action"),
    [
        (
            "subtle",
            f"- Brand: Acme Tools, subtle: {BRAND_CHOICE_LINES['subtle']}",
            '- Call to action: "Start planning today" (with no link)',
        ),
        (
            "none",
            f"- Brand: Acme Tools, none: {BRAND_CHOICE_LINES['none']}",
            '- Call to action: "Start planning today" (with no link)',
        ),
    ],
)
def test_each_brand_choice_says_what_the_article_does(prominence, brand_line, call_to_action):
    brief, _ = _brief(_outline(prominence))
    lines = render_generation_brief(brief, stage="writer").splitlines()

    assert brand_line in lines and call_to_action in lines


def test_a_mention_approved_before_the_levels_existed_is_still_a_mention():
    brief, _ = _brief(_outline(None, promote_brand=True))

    assert brief["brand_choice"] == "mention"
    assert "- Brand: Acme Tools, mentioned where this kind of article places it" in (
        render_generation_brief(brief, stage="writer")
    )


def test_without_a_brand_or_a_choice_the_brief_says_nothing_about_one():
    no_brand, _ = _brief(_outline("none", brand_voice_promotion={}))
    not_promoted, _ = _brief(_outline(None))
    # "None" with a keyphrase that is the brand's own name is not an exclusion (the spec).
    outline = _outline("none", focus_keyphrase="acme tools login")
    spec = build_requirements_spec(outline, "blog", focus_keyword="acme tools login")
    branded = build_generation_brief(spec, outline)

    assert spec["excluded_brand"] is None
    for brief in (no_brand, not_promoted, branded):
        assert brief["brand_choice"] == "" and brief["brand_name"] == ""
        assert "- Brand:" not in render_generation_brief(brief, stage="writer")


def test_an_empty_fact_adds_no_line():
    spec = build_requirements_spec({"title": TITLE}, "blog")
    text = render_generation_brief(build_generation_brief(spec, {"title": TITLE}), stage="rewrite")

    assert text.splitlines()[4:] == [
        f'- Title (fixed, the user chose it): "{TITLE}"',
        "- Content type: blog",
    ]


@pytest.mark.parametrize("prominence", ["none", "subtle"])
def test_a_call_to_action_that_names_the_brand_is_given_as_an_intent_to_reword(prominence):
    outline = _outline(prominence, final_cta={"primary_cta": "Get started with Acme Tools"})
    brief, _ = _brief(outline)
    text = render_generation_brief(brief, stage="rewrite")

    assert brief["call_to_action_without"] == "Acme Tools"
    assert brief["call_to_action_links"] is False
    assert (
        '- Call to action: the same intent as the outline\'s ("Get started with Acme Tools"), '
        "in new words without Acme Tools, and with no link"
    ) in text
    # With a prominent mention the same call to action is kept as written, link and all.
    kept, _ = _brief(
        _outline("prominent", final_cta={"primary_cta": "Get started with Acme Tools"})
    )
    assert '- Call to action: "Get started with Acme Tools"' in (
        render_generation_brief(kept, stage="rewrite").splitlines()
    )


def test_a_keyphrase_that_is_the_brands_own_still_gets_a_brand_free_call_to_action():
    """ "None" with a branded keyphrase is no exclusion, so the brief has no brand line; the
    call to action is brand-free all the same, as the spec, the cleanup and the writer hold."""
    outline = _outline(
        "none",
        focus_keyphrase="acme tools login",
        final_cta={"primary_cta": "Get started with Acme Tools"},
    )
    spec = build_requirements_spec(outline, "blog", focus_keyword="acme tools login")
    brief = build_generation_brief(spec, outline)
    text = render_generation_brief(brief, stage="writer")

    assert spec["excluded_brand"] is None and spec["cta_without_link"] is True
    assert "- Brand:" not in text
    assert brief["call_to_action_without"] == "Acme Tools" and not brief["call_to_action_links"]
    assert "in new words without Acme Tools, and with no link" in text


def test_every_keyword_the_spec_checks_is_in_the_brief():
    many = [FOCUS, *[f"keyword {index}" for index in range(30)]]
    brief, spec = _brief(_outline("prominent", keywords_to_include=many))

    assert len(spec["secondary_keywords"]) == 30
    assert brief["secondary_keywords"] == spec["secondary_keywords"]
