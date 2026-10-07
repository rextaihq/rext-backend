"""The outline prompt asks for H3 subsections where the content type can hold them (rext-control#603).

On staging 7 of 8 outlines came back with H2s only, a pillar guide and a regeneration whose
feedback asked for H3s among them: the prompt said to use H3s "only when logically required".
These cover the rule each content type gets, feedback that asks for subsections, the blog
schema's room for them, and the rule reaching the outline model's prompt.
"""

import pytest
from pydantic import ValidationError

import src.flow.engines.content.generation.outline as outline_module
from src.flow.model.structure.outlines.infomational.blog import BlogOutline, ContentStructure
from src.flow.prompts.human.outline import (
    get_outline_prompt,
    outline_subsection_rule,
    subsection_request,
)

FIXED_SHAPE_TYPES = [
    "best-tools",
    "product-roundup",
    "resource-list",
    "alternatives",
    "comparison",
    "checklist",
    "faq",
    "glossary",
]


@pytest.mark.unit
def test_pillar_content_expects_subsections():
    rule = outline_subsection_rule("pillar-content")

    assert "EXPECTED for this content type" in rule
    assert "at least half of the H2s" in rule
    assert "MUST" not in rule


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ["blog", "Blog", "article", None])
def test_a_blog_decides_by_its_shape(content_type):
    rule = outline_subsection_rule(content_type)

    assert "decide by the article's shape" in rule
    assert "A long blog or guide" in rule and "EXPECTED" in rule
    assert "A short blog" in rule and "OPTIONAL" in rule
    assert "A list article" in rule and "NONE" in rule
    assert "at most 16 entries in all" in rule


@pytest.mark.unit
def test_a_listicle_gets_no_subsections():
    """ "listicle" runs as a blog, but its items are the H2s."""
    rule = outline_subsection_rule("blog", "Listicle")

    assert rule.startswith("H3 SUBSECTIONS: NONE by default. This is a list article")
    assert "EXPECTED" not in rule
    assert "candidates for its H3s" not in rule


@pytest.mark.unit
def test_a_listicle_gets_h3s_when_the_reviewer_asks():
    """Review round 2: a listicle runs on the blog schema, which holds H3s."""
    rule = outline_subsection_rule("blog", "listicle", feedback="Add H3s under each list item")

    assert "this pass MUST contain H3s" in rule
    assert "can't nest headings" not in rule
    assert "first candidates for its H3s" in rule


@pytest.mark.unit
@pytest.mark.parametrize("content_type", FIXED_SHAPE_TYPES)
def test_fixed_shape_types_get_no_subsections(content_type):
    rule = outline_subsection_rule(content_type)

    assert rule.startswith("H3 SUBSECTIONS: NONE for this content type")
    assert "each step, item or block you fill becomes a heading of its own" in rule
    assert "Plan 3-10 steps" not in rule
    assert "candidates for its H3s" not in rule  # review round 2: no H3s nominated here


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ["blog", "pillar-content"])
def test_the_cluster_sub_topics_are_named_where_h3s_belong(content_type):
    assert "first candidates for its H3s" in outline_subsection_rule(content_type)


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ["how-to-guide", "How To Guide", "tutorial"])
def test_step_guides_plan_several_steps(content_type):
    """A How-To came back with one step (rext-control#603, 08:28Z comment)."""
    rule = outline_subsection_rule(content_type)

    assert rule.startswith("H3 SUBSECTIONS: NONE for this content type")
    assert "Plan 3-10 steps. A one-step guide is not a guide" in rule


@pytest.mark.unit
@pytest.mark.parametrize(
    "feedback",
    [
        "Add H3s under each section",
        "each tool as its own H3",
        "It needs subsections",
        "use sub-headings for the steps",
        "Break the long sections into sub sections",
        "nested headings please",
        "No, add H3s under the tools",
        "Not detailed enough: add H3s",
        "Drop the H3 under the intro. Add H3s to the tools section.",
        "The H3s are missing",
        "H3s under each list item",
        "Subsections for pricing and features",
    ],
)
def test_feedback_asking_for_subsections_is_recognised(feedback):
    assert subsection_request(feedback) == "more"


@pytest.mark.unit
@pytest.mark.parametrize(
    "feedback",
    [
        "Remove the H3s",
        "do not use subsections",
        "Don't want any sub-headings",
        "Too many H3s",
        "no subsections please",
        "Flatten it: without nested headings",
        "The H3s aren't needed",
        "the subsections are unnecessary",
        "the sub-headings should go",
        "The H3s need to be removed",
        "H3s must be removed",
        "the subsections should be taken out",
        "I don't think the H3s are needed",
        "Not sure the sub-headings are really necessary",
        "I don't think that any of the H3s are needed",
    ],
)
def test_feedback_asking_for_fewer_subsections_is_recognised(feedback):
    """Review round 1: "Remove the H3s" must not turn into "this pass MUST contain H3s"."""
    assert subsection_request(feedback) == "fewer"


@pytest.mark.unit
@pytest.mark.parametrize(
    "feedback",
    [
        None,
        "",
        "None",
        "Make it shorter",
        "Change the tone",
        "Add a section on pricing",
        'Rename the H3 "Cost" to "Pricing"',
        "The H3s aren't detailed enough",
        "The H3 is not specific enough",
        "I don't think the H3s are detailed enough",
        "I don't think the H3s are helpful enough",
        "Not sure the subsections are useful enough yet",
        "I don't think the H3s should be removed",
        "The H3 under the intro is too long",
    ],
)
def test_other_feedback_says_nothing_about_subsections(feedback):
    """A mention needs a cue either way: a rename or a quality note leaves the structure alone."""
    assert subsection_request(feedback) is None


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ["blog", "pillar-content"])
def test_feedback_asking_for_fewer_subsections_is_followed(content_type):
    rule = outline_subsection_rule(content_type, feedback="Remove the H3s")

    assert "asks for fewer or no subsections: follow it" in rule
    assert "MUST contain H3s" not in rule


@pytest.mark.unit
def test_feedback_asking_for_fewer_on_a_fixed_shape_adds_nothing():
    assert "feedback" not in outline_subsection_rule("best-tools", feedback="Too many H3s")


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ["blog", "pillar-content"])
def test_feedback_asking_for_subsections_makes_them_required(content_type):
    rule = outline_subsection_rule(content_type, feedback="Please add H3 subsections")

    assert "this pass MUST contain H3s" in rule
    assert "at least two H2s with H3s" in rule


@pytest.mark.unit
def test_feedback_asking_for_subsections_on_a_fixed_shape_is_answered_inside_the_items():
    rule = outline_subsection_rule("best-tools", feedback="each tool as its own H3")

    assert "can't nest headings" in rule
    assert "already gets a heading of its own" in rule
    assert "MUST contain H3s" not in rule


@pytest.mark.unit
def test_no_feedback_adds_no_requirement():
    assert "feedback" not in outline_subsection_rule("blog", feedback="None")


def _prompt_values(**overrides):
    values = {
        "content_type": "blog",
        "topic": "Email marketing for small businesses",
        "related_topics": "",
        "questions": "",
        "competitors_context": "",
        "known_entities": "",
        "reader_and_offer": "None available.",
        "intent_distribution": "Informational",
        "keyword_clusters": "None",
        "cluster_heading_map": "None.",
        "subsection_rule": outline_subsection_rule("blog"),
        "rejected_reason": "None",
        "previous_outline": {},
    }
    return {**values, **overrides}


@pytest.mark.unit
def test_the_rule_replaces_the_old_only_when_required_line():
    human = get_outline_prompt().format_messages(**_prompt_values())[1].content

    assert (
        "4b. Subsections, for this content type:\nH3 SUBSECTIONS: decide by the article's shape."
        in human
    )
    assert "H3 sections only when logically required" not in human
    assert "{subsection_rule}" not in human


def _section(heading, level="H2"):
    return {
        "heading": heading,
        "heading_level": level,
        "description": "d",
        "key_points": ["a", "b"],
    }


@pytest.mark.unit
def test_a_blog_outline_has_room_for_h3s():
    """5 H2s and 9 H3s, like the one staging outline that had subsections, now fit."""
    sections = []
    for h2 in range(5):
        sections.append(_section(f"Main {h2}"))
        sections.extend(_section(f"Part {h2}.{h3}", "H3") for h3 in range(2 if h2 < 4 else 1))

    assert len(ContentStructure(sections=sections).sections) == 14


@pytest.mark.unit
@pytest.mark.parametrize("count", [3, 17])
def test_a_blog_outline_stays_bounded(count):
    with pytest.raises(ValidationError):
        ContentStructure(sections=[_section(f"S {i}") for i in range(count)])


@pytest.mark.unit
def test_the_extra_room_is_for_h3s_not_more_h2s():
    """Review round 1: 9-16 entries all H2 are refused, as they were under the 8-entry cap."""
    with pytest.raises(ValidationError, match="at most 8 H2 sections, got 9"):
        ContentStructure(sections=[_section(f"S {i}") for i in range(9)])

    full = [_section(f"S {i}", "H2" if i % 2 == 0 else "H3") for i in range(16)]
    assert len(ContentStructure(sections=full).sections) == 16


@pytest.mark.unit
def test_an_outline_that_passed_before_still_passes():
    """Fewer than four H2s with H3s made up four entries before; no new refusal."""
    sections = [_section("A"), _section("A.1", "H3"), _section("B"), _section("B.1", "H3")]
    assert len(ContentStructure(sections=sections).sections) == 4


class _Stop(Exception):
    pass


async def _outline_prompt_for(monkeypatch, content_type, rejected_reason="None"):
    """The human message generate_outline sends the outline model, with the model call stopped."""
    sent = []

    class _Model:
        def with_structured_output(self, _schema):
            return self

        async def ainvoke(self, messages):
            sent.extend(messages)
            raise _Stop

    async def _no_entities(_workspace_id):
        return "", []

    async def _no_sync(_workspace_id):
        return None

    monkeypatch.setattr(outline_module, "load_model", lambda **_kw: _Model())
    monkeypatch.setattr(outline_module, "_fetch_known_entities", _no_entities)
    monkeypatch.setattr(outline_module, "_bulk_sync_workspace", _no_sync)
    monkeypatch.setattr(outline_module, "resolve_focus_keyword", lambda _state: "email marketing")
    monkeypatch.setattr(
        outline_module, "build_cluster_heading_map", lambda **_kw: {"enabled": False}
    )

    state = {
        "serp_payload": {"workspace_id": None},
        "content": {
            "selected_topic": "Email marketing for small businesses",
            "content_type": content_type,
            "outline": {"rejected_reason": rejected_reason},
        },
    }
    result = await outline_module.generate_outline.__wrapped__(state)

    assert "error" in result["content"]  # stopped at the model call
    return sent[1].content


@pytest.mark.unit
async def test_generate_outline_sends_the_rule_for_its_content_type(monkeypatch):
    human = await _outline_prompt_for(monkeypatch, "Pillar Content")

    assert "H3 SUBSECTIONS: EXPECTED for this content type." in human


@pytest.mark.unit
async def test_generate_outline_sends_the_feedback_requirement(monkeypatch):
    human = await _outline_prompt_for(monkeypatch, "blog", rejected_reason="Add H3s please")

    assert "Previous Rejection Reason: Add H3s please" in human
    assert "this pass MUST contain H3s" in human


@pytest.mark.unit
@pytest.mark.parametrize("content_type", ["ultimate-roundup", "Something New"])
def test_an_unknown_type_gets_the_blog_rule_like_its_schema(content_type):
    """get_outline_model writes an unknown type on the blog schema, which holds H3s."""
    assert outline_subsection_rule(content_type).startswith(
        "H3 SUBSECTIONS: decide by the article's shape."
    )
    assert "this pass MUST contain H3s" in outline_subsection_rule(content_type, feedback="Add H3s")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("budgets", "expected"),
    [
        ([800] * 16, 5000),  # 8 H2s and 8 H3s with large budgets: the schema's 5,000 cap
        ([100] * 4, 800),  # a thin plan still asks for the blog's 800 minimum
        ([300, 250, 400, 350, None], 1500),  # an unset budget counts as 200
    ],
)
def test_the_summed_word_target_stays_inside_the_blog_limits(budgets, expected):
    """Review round 3 of #890: 16 entries could sum past BlogOutline's 5,000-word limit."""
    sections = [{"suggested_word_count": budget} for budget in budgets]

    assert outline_module._summed_word_target(BlogOutline, sections) == expected


@pytest.mark.unit
def test_the_summed_word_target_is_the_plain_sum_without_schema_limits():
    assert outline_module._summed_word_target(object, [{"suggested_word_count": 9000}, "x"]) == 9000
