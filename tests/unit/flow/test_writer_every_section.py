"""The writer writes every planned section, in order; a dropped one fails validation.

rext-control#329. Blog's whole body is one outline block (`structure`, a list of
sections). The writer got one field for it and wrote one heading with the
planned sections folded under it: a four-section outline came back as two H2s.
Each planned section of a container is now a writer field of its own, assembled
in the approved order, and validation blocks an article that drops one.
"""

import re

import pytest

from src.flow.engines.content.generation.brand_schema_context import (
    resolve_brand_schema_context,
)
from src.flow.engines.content.generation.brand_slot import (
    SLOT_BLOCK_KEYS,
    SLOT_LINE_PREFIX,
    SLOT_SECTION_INDEX,
)
from src.flow.engines.content.generation.outline_structure import (
    MAX_EXPANDED_SECTIONS,
    expand_section_containers,
    resolve_outline_structure,
)
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.structured_body import (
    STRUCTURED_BLOCKS_KEY,
    assemble_structured_payload,
    build_structured_content_model,
)
from src.flow.engines.content.generation.validation import check_required_sections
from src.flow.model.structure.contents import get_generated_content_model

SECTIONS = [
    ("Why content marketing ROI is hard to measure", ["attribution gaps", "long sales cycles"]),
    ("The metrics small businesses should track", ["leads per post", "cost per lead"]),
    ("How to set up tracking in an afternoon", ["UTM tags", "goal setup in analytics"]),
    ("Turning the numbers into a content budget", ["payback period", "monthly budget"]),
]


def _section(heading, points, level="H2"):
    return {
        "heading": heading,
        "heading_level": level,
        "description": f"Explain {heading.lower()}.",
        "key_points": points,
        "suggested_word_count": 400,
    }


def _blog_outline(sections=SECTIONS, **extra):
    return {
        "title": "Content Marketing ROI for Small Business: A Practical Guide",
        "structure": {"sections": [_section(h, p) for h, p in sections]},
        **extra,
    }


def _model(outline, content_type):
    built = build_structured_content_model(
        outline, content_type, get_generated_content_model(content_type)
    )
    assert built is not None
    return built


@pytest.mark.parametrize(
    ("content_type", "outline", "container", "headings"),
    [
        ("blog", _blog_outline(), "structure", [h for h, _ in SECTIONS]),
        (
            "pillar-content",
            {"structure": {"sections": [_section(h, p) for h, p in SECTIONS[:3]]}},
            "structure",
            [h for h, _ in SECTIONS[:3]],
        ),
    ],
    ids=["blog", "pillar-content"],
)
def test_each_planned_section_is_a_required_writer_field_in_order(
    content_type, outline, container, headings
):
    model, blocks = _model(outline, content_type)

    keys = [f"{container}_{i}" for i in range(1, len(headings) + 1)]
    assert [b.key for b in blocks if b.parent == container] == keys
    assert [b.heading for b in blocks if b.parent == container] == headings
    assert container not in model.model_fields
    for i, key in enumerate(keys):
        field = model.model_fields[key]
        assert field.is_required()
        assert f"Planned section {i + 1} of {len(keys)}: {headings[i]!r}" in field.description
    # The schema lists them in the approved order, which is the order the
    # writer fills them in.
    order = list(model.model_fields)
    assert [order.index(k) for k in keys] == sorted(order.index(k) for k in keys)


HOW_TO = {
    "steps": {
        "steps": [
            {"title": "Install the tracking snippet", "description": "Add it to every page."},
            {"title": "Tag your campaign links", "description": "Use UTM parameters."},
        ]
    },
    "tools": {"tools": [{"name": "Google Analytics", "purpose": "Reports", "required": True}]},
}


def test_how_to_steps_are_no_prose_blocks_and_lists_of_entries_stay_whole():
    # The steps block stays with the typed `steps` list, which the article shows as one
    # numbered list, and a tool list is the content of one section, not a section per tool.
    model, blocks = _model(HOW_TO, "how-to-guide")

    assert not [b for b in blocks if b.parent]
    assert not [f for f in model.model_fields if re.fullmatch(r"(steps|tools)_\d+", f)]
    spec = build_requirements_spec(HOW_TO, "how-to-guide", focus_keyword="tracking")
    assert spec["planned_sections"] == []


def test_each_approved_step_of_a_how_to_guide_is_a_required_field_in_the_approved_order():
    """The typed list alone left the writer to its own four to six one-sentence steps
    (rext-control #817): each approved step is asked for by name."""
    model, _ = _model(HOW_TO, "how-to-guide")

    step_fields = [f for f in model.model_fields if re.fullmatch(r"step_\d+", f)]
    assert step_fields == ["step_1", "step_2"]
    assert all(model.model_fields[f].is_required() for f in step_fields)
    first, second = (model.model_fields[f].description for f in step_fields)
    assert "Step 1 of 2" in first and "'Install the tracking snippet'" in first
    assert "Step 2 of 2" in second and "'Tag your campaign links'" in second
    # What the outline planned for the step is on the step's own field.
    assert "Add it to every page." in first and "Use UTM parameters." in second
    # The free list is no longer asked for.
    assert not model.model_fields["steps"].is_required()
    assert "Leave this empty" in model.model_fields["steps"].description


def test_a_steps_plan_carries_its_expected_result_its_warning_and_its_tips():
    outline = {
        "steps": {
            "steps": [
                {
                    "title": "Remove the plant from its pot",
                    "description": "Tip the pot and ease the root ball out.",
                    "expected_result": "The root ball comes out whole.",
                    "warning": "Never pull the plant by its stem.",
                    "tips": ["Water it the day before", " "],
                }
            ]
        }
    }
    model, _ = _model({**HOW_TO, **outline}, "how-to-guide")

    description = model.model_fields["step_1"].description
    assert "Expected result: The root ball comes out whole." in description
    assert "Warning: Never pull the plant by its stem." in description
    assert "Tips to work in: Water it the day before" in description


def test_the_order_of_the_approved_list_is_the_steps_order_whatever_their_numbers_say():
    """A reorder at the outline step leaves `step_number` as it was written."""
    steps = [
        {"step_number": 2, "title": "Tag your campaign links", "description": "UTM."},
        {"step_number": 1, "title": "Install the tracking snippet", "description": "Add it."},
    ]
    model, _ = _model({**HOW_TO, "steps": {"steps": steps}}, "how-to-guide")

    assert "'Tag your campaign links'" in model.model_fields["step_1"].description
    assert "'Install the tracking snippet'" in model.model_fields["step_2"].description


def test_two_how_to_guides_never_share_a_model():
    other = {**HOW_TO, "steps": {"steps": [{"title": "Open the report", "description": "Go."}]}}

    first, _ = _model(HOW_TO, "how-to-guide")
    second, _ = _model(other, "how-to-guide")

    assert "step_2" in first.model_fields and "step_2" not in second.model_fields
    assert "'Open the report'" in second.model_fields["step_1"].description


@pytest.mark.parametrize(
    "steps",
    [
        [],
        [{"title": "", "description": "No title"}, {"title": "Second", "description": "x"}],
        [{"title": f"Step {n}", "description": "x"} for n in range(1, 23)],
    ],
)
def test_an_outline_without_a_usable_list_of_steps_keeps_the_typed_list(steps):
    model, _ = _model({**HOW_TO, "steps": {"steps": steps}}, "how-to-guide")

    assert not [f for f in model.model_fields if re.fullmatch(r"step_\d+", f)]
    assert "Leave this empty" not in (model.model_fields["steps"].description or "")


def test_another_article_type_gets_no_step_fields():
    model, _ = _model(_blog_outline(), "blog")

    assert not [f for f in model.model_fields if re.fullmatch(r"step_\d+", f)]


def test_a_sections_plan_is_on_its_own_field_and_bookkeeping_is_not():
    model, _ = _model(_blog_outline(), "blog")

    description = model.model_fields["structure_2"].description
    assert "The metrics small businesses should track" in description
    assert "leads per post" in description and "cost per lead" in description
    assert "400" not in description  # suggested_word_count is the pipeline's, not the writer's


def test_a_long_pillar_outline_gets_a_field_per_section():
    sections = [{**_section(f"Pillar chapter {i}", ["a point"])} for i in range(1, 16)]
    model, blocks = _model({"structure": {"sections": sections}}, "pillar-content")

    assert [b.key for b in blocks if b.parent] == [f"structure_{i}" for i in range(1, 16)]


def test_an_outline_beyond_the_schema_guard_stays_one_field():
    sections = [(f"Entry {i}", ["a point"]) for i in range(MAX_EXPANDED_SECTIONS + 1)]
    blocks = expand_section_containers(resolve_outline_structure(_blog_outline(sections), "blog"))

    assert [b.key for b in blocks] == ["structure"]


def test_the_article_is_assembled_in_the_approved_order_with_its_levels():
    outline = _blog_outline()
    outline["structure"]["sections"][3]["heading_level"] = "H3"
    _, blocks = _model(outline, "blog")
    generated = {
        f"structure_{i}": {"heading": heading, "markdown": f"Prose for section {i}."}
        for i, (heading, _) in enumerate(SECTIONS, 1)
    }
    generated["structure_3"]["markdown"] = "   "  # written empty: as missing as absent

    payload = assemble_structured_payload({"title": "T", **generated}, blocks)

    body = payload["body_markdown"]
    assert body.index(SECTIONS[0][0]) < body.index(SECTIONS[1][0]) < body.index(SECTIONS[3][0])
    assert f"## {SECTIONS[0][0]}" in body and f"### {SECTIONS[3][0]}" in body
    assert SECTIONS[2][0] not in body
    assert "structure_3" not in payload[STRUCTURED_BLOCKS_KEY]


def test_an_h4_planned_section_is_written_and_checked_as_an_h4():
    sections = [
        _section("Choosing a platform", ["cost"]),
        _section("Pricing tiers", ["plans"], "H4"),
    ]
    outline = {"structure": {"sections": sections}}
    _, blocks = _model(outline, "pillar-content")
    assert [b.level for b in blocks if b.parent] == [2, 4]

    payload = assemble_structured_payload(
        {
            "title": "T",
            "structure_1": {"heading": "Choosing a platform", "markdown": "About cost."},
            "structure_2": {"heading": "Pricing tiers", "markdown": "About plans."},
        },
        blocks,
    )
    assert "#### Pricing tiers" in payload["body_markdown"]

    spec = build_requirements_spec(outline, "pillar-content", focus_keyword="platform")
    assert [p["level"] for p in spec["planned_sections"]] == [2, 4]
    flattened = _article(("##", "Choosing a platform", "cost"), ("##", "Pricing tiers", "plans"))
    assert not check_required_sections(flattened, spec)["passed"]


def test_the_brand_mention_targets_only_the_section_the_slot_chose():
    outline = _blog_outline(
        promote_brand=True,
        brand_voice_promotion={
            "brand_name": "Rext",
            SLOT_BLOCK_KEYS: ["structure"],
            SLOT_SECTION_INDEX: 1,
        },
    )
    sections = outline["structure"]["sections"]
    sections[1]["key_points"].append(f"{SLOT_LINE_PREFIX} Rext here.")
    sections[3]["key_points"].append("Compare Rext with the other tools")  # named, not the slot
    blocks = expand_section_containers(resolve_outline_structure(outline, "blog"))

    context = resolve_brand_schema_context(outline, "blog", blocks)

    assert set(context.field_directives) == {"structure_2"}

    # An outline approved before the slot recorded its index: the slot's own line decides.
    del outline["brand_voice_promotion"][SLOT_SECTION_INDEX]
    context = resolve_brand_schema_context(outline, "blog", blocks)
    assert set(context.field_directives) == {"structure_2"}


def _article(*sections):
    return {"body_markdown": "\n\n".join(f"{marker} {h}\n\n{text}" for marker, h, text in sections)}


def _spec():
    return build_requirements_spec(_blog_outline(), "blog", focus_keyword="content marketing roi")


def test_an_article_with_every_planned_section_passes():
    article = _article(*(("##", h, " ".join(p)) for h, p in SECTIONS))

    assert check_required_sections(article, _spec())["passed"]


def test_a_dropped_planned_section_blocks_and_names_where_it_goes():
    article = _article(*(("##", h, " ".join(p)) for h, p in SECTIONS if h != SECTIONS[2][0]))

    result = check_required_sections(article, _spec())

    assert not result["passed"] and result["severity"] == "blocking"
    assert SECTIONS[2][0] in result["detail"]
    assert "section 3 of 4" in result["detail"]
    assert f"between {SECTIONS[1][0]!r} and {SECTIONS[3][0]!r}" in result["detail"]
    assert "UTM tags" in result["detail"]  # what the section covers, for repair


def test_a_planned_section_folded_under_another_as_an_h3_blocks():
    # The collapse #329 found: four planned H2s, written as two H2s with H3s.
    article = _article(
        ("##", SECTIONS[0][0], "attribution gaps, long sales cycles"),
        ("###", SECTIONS[1][0], "leads per post, cost per lead"),
        ("##", SECTIONS[2][0], "UTM tags, goal setup in analytics"),
        ("###", SECTIONS[3][0], "payback period, monthly budget"),
    )

    result = check_required_sections(article, _spec())

    assert not result["passed"] and result["severity"] == "blocking"
    assert SECTIONS[1][0] in result["detail"] and SECTIONS[3][0] in result["detail"]


def test_a_reworded_heading_counts_when_the_section_covers_its_plan():
    article = _article(
        ("##", SECTIONS[0][0], "attribution gaps and long sales cycles"),
        ("##", "What to count each month", "Track leads per post and cost per lead, monthly."),
        ("##", SECTIONS[2][0], "UTM tags, goal setup in analytics"),
        ("##", SECTIONS[3][0], "payback period, monthly budget"),
    )

    assert check_required_sections(article, _spec())["passed"]


def test_planned_sections_out_of_the_approved_order_block():
    article = _article(
        *(("##", h, " ".join(p)) for h, p in [SECTIONS[0], SECTIONS[2], SECTIONS[1], SECTIONS[3]])
    )

    result = check_required_sections(article, _spec())

    assert not result["passed"] and result["severity"] == "blocking"
    assert "out of the approved order" in result["detail"]


def test_a_planned_subsection_under_the_wrong_section_blocks():
    outline = _blog_outline()
    outline["structure"]["sections"][1]["heading_level"] = "H3"  # planned under section 1
    spec = build_requirements_spec(outline, "blog", focus_keyword="content marketing roi")
    article = _article(
        ("##", SECTIONS[0][0], "attribution gaps, long sales cycles"),
        ("##", SECTIONS[2][0], "UTM tags, goal setup in analytics"),
        ("###", SECTIONS[1][0], "leads per post, cost per lead"),  # under section 3 instead
        ("##", SECTIONS[3][0], "payback period, monthly budget"),
    )

    result = check_required_sections(article, spec)

    assert not result["passed"] and "out of the approved order" in result["detail"]


def test_an_optional_legacy_sections_list_is_still_checked_by_heading():
    # A flat top-level `sections` list no schema declares is kept as an optional
    # block: its sections aren't required, but dropping all of them still fails.
    outline = {"sections": [_section(h, p) for h, p in SECTIONS]}
    spec = build_requirements_spec(outline, "blog", focus_keyword="content marketing roi")
    assert spec["planned_sections"] and not any(p["required"] for p in spec["planned_sections"])

    result = check_required_sections(_article(("##", "Something else entirely", "text")), spec)

    assert not result["passed"]


# --- the writer keeps what the user approved (G70 #586, G71 #587) -------------


def test_a_heading_the_user_reworded_is_written_word_for_word():
    """The model's own wording replaced the user's; an unedited heading keeps its latitude."""
    from src.flow.engines.content.review.outline_edits import apply_section_edits

    rows = [{"id": f"structure.sections:{i}"} for i in range(4)]
    rows[1]["heading"] = "What to track first"
    outline = apply_section_edits(_blog_outline(), "blog", rows)
    _, blocks = _model(outline, "blog")
    generated = {
        f"structure_{i}": {"heading": f"Model heading {i}", "markdown": f"Prose {i}."}
        for i in range(1, 5)
    }

    body = assemble_structured_payload({"title": "T", **generated}, blocks)["body_markdown"]

    assert "## What to track first" in body
    assert "## Model heading 1" in body  # not edited by the user: the model's wording stands
    assert "Model heading 2" not in body


def test_a_planned_faq_section_is_the_only_place_the_faqs_go():
    """The outline's FAQ list beside a planned FAQ section was a second required block."""
    faqs = {"faqs": [{"question": "How often should I measure ROI?", "answer": "Monthly."}]}
    with_section = _blog_outline(
        sections=[*SECTIONS, ("FAQs on content marketing ROI", ["common questions"])], faqs=faqs
    )
    model, blocks = _model(with_section, "blog")

    assert "faqs" not in model.model_fields
    assert not any(block.key == "faqs" for block in blocks)
    faq_field = model.model_fields["structure_5"]
    assert "This is the article's FAQ section" in faq_field.description

    without_section = _blog_outline(faqs=faqs)
    model, _ = _model(without_section, "blog")
    assert "faqs" in model.model_fields

    # A topic that starts with "FAQ-" isn't the FAQ section: the FAQs keep their own block.
    topical = _blog_outline(
        sections=[*SECTIONS, ("FAQ-driven content strategy", ["answer pages"])], faqs=faqs
    )
    model, _ = _model(topical, "blog")
    assert "faqs" in model.model_fields
    assert "This is the article's FAQ section" not in model.model_fields["structure_4"].description
