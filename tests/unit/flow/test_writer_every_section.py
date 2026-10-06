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
from src.flow.engines.content.generation.brand_slot import SLOT_BLOCK_KEYS
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


def test_how_to_steps_stay_with_their_typed_field_and_lists_of_entries_stay_whole():
    # how-to-guide's content model writes steps through its typed `steps` list,
    # and a tool list is the content of one section, not a section per tool.
    model, blocks = _model(HOW_TO, "how-to-guide")

    assert not [b for b in blocks if b.parent]
    assert not [f for f in model.model_fields if re.fullmatch(r"(steps|tools)_\d+", f)]
    spec = build_requirements_spec(HOW_TO, "how-to-guide", focus_keyword="tracking")
    assert spec["planned_sections"] == []


def test_a_sections_plan_is_on_its_own_field_and_bookkeeping_is_not():
    model, _ = _model(_blog_outline(), "blog")

    description = model.model_fields["structure_2"].description
    assert "The metrics small businesses should track" in description
    assert "leads per post" in description and "cost per lead" in description
    assert "400" not in description  # suggested_word_count is the pipeline's, not the writer's


def test_a_long_list_of_entries_stays_one_field():
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


def test_the_brand_mention_targets_the_section_the_slot_chose():
    outline = _blog_outline(
        promote_brand=True,
        brand_voice_promotion={"brand_name": "Rext", SLOT_BLOCK_KEYS: ["structure"]},
    )
    outline["structure"]["sections"][1]["key_points"].append(
        "Work in the approved mention of Rext here."
    )
    blocks = expand_section_containers(resolve_outline_structure(outline, "blog"))

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
