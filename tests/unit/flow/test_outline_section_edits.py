"""The outline gate accepts the user's section order, headings and removals.

The rows the gate offers are the headings the article is written and checked
against; an approved order reaches the writer's plan and the validator's
expected headings unchanged.
"""

import copy

import src.flow.engines.content.review.outline as review_module
from src.flow.engines.content.generation.content_generation import (
    _format_outline_for_generation,
)
from src.flow.engines.content.generation.outline_structure import (
    resolve_expected_headings,
    resolve_outline_structure,
)
from src.flow.engines.content.review.outline_edits import (
    apply_section_edits,
    editable_sections,
)


def _section(heading, level="H2"):
    return {
        "heading": heading,
        "heading_level": level,
        "description": f"What {heading} covers.",
        "key_points": [f"{heading} point one", f"{heading} point two"],
        "suggested_word_count": 200,
    }


def _blog_outline():
    return {
        "title": "Running shoes for beginners",
        "hero": {"headline": "Running shoes for beginners", "subheadline": "How to choose."},
        "structure": {
            "sections": [
                _section("Why the right shoe matters"),
                _section("Cushioning and support"),
                _section("Heel drop explained", "H3"),
                _section("How to get fitted"),
            ]
        },
        "faqs": {"faqs": [{"question": "How often should I replace them?", "answer": "Often."}]},
        "_render": {"blocks": []},
    }


BLOG_IDS = [f"structure.sections:{i}" for i in range(4)]


def _headings(outline, path=("structure", "sections")):
    node = outline
    for key in path:
        node = node[key]
    return [item["heading"] for item in node]


# --- what the gate offers ----------------------------------------------------


def test_gate_offers_each_body_section_with_a_stable_id():
    rows = editable_sections(_blog_outline(), "blog")

    assert [row["id"] for row in rows] == BLOG_IDS
    assert [row["heading"] for row in rows] == _headings(_blog_outline())
    assert {row["list"] for row in rows} == {"structure.sections"}
    assert [row["heading_level"] for row in rows] == ["H2", "H2", "H3", "H2"]


def test_hero_and_faqs_are_not_offered():
    rows = editable_sections(_blog_outline(), "blog")

    assert all(not row["id"].startswith(("hero", "faqs")) for row in rows)


def test_a_flat_sections_list_is_offered_too():
    outline = {"title": "T", "sections": [_section("One"), _section("Two")]}

    assert [row["id"] for row in editable_sections(outline, "blog")] == [
        "sections:0",
        "sections:1",
    ]


# --- what approval applies ---------------------------------------------------


def test_reorder_and_rename():
    outline = _blog_outline()
    before = copy.deepcopy(outline)
    rows = [
        {"id": BLOG_IDS[3], "heading": "Get fitted first"},
        {"id": BLOG_IDS[0]},
        {"id": BLOG_IDS[1], "heading": "  "},
        {"id": BLOG_IDS[2]},
    ]

    edited = apply_section_edits(outline, "blog", rows)

    assert _headings(edited) == [
        "Get fitted first",
        "Why the right shoe matters",
        "Cushioning and support",
        "Heel drop explained",
    ]
    # the rest of each section travels with its heading
    assert edited["structure"]["sections"][0]["key_points"][0] == "How to get fitted point one"
    assert outline == before  # the input is not changed
    assert edited["hero"] == outline["hero"] and edited["faqs"] == outline["faqs"]


def test_an_unnamed_section_is_removed():
    edited = apply_section_edits(
        _blog_outline(), "blog", [{"id": BLOG_IDS[0]}, {"id": BLOG_IDS[3]}]
    )

    assert _headings(edited) == ["Why the right shoe matters", "How to get fitted"]


def test_heading_level_can_change_and_a_leading_subsection_becomes_a_section():
    edited = apply_section_edits(
        _blog_outline(),
        "blog",
        [{"id": BLOG_IDS[2]}, {"id": BLOG_IDS[0], "heading_level": "H3"}, {"id": BLOG_IDS[1]}],
    )

    levels = [s["heading_level"] for s in edited["structure"]["sections"]]
    assert levels == ["H2", "H3", "H2"]


def test_bad_rows_change_nothing():
    outline = _blog_outline()
    for rows in (
        None,
        [],
        "approve",
        [{"id": "nowhere:0"}],
        [{"id": "structure.sections:9"}],
        [{"id": "structure.sections"}, {"heading": "no id"}, "row"],
        [{"id": "hero:0"}],
    ):
        assert _headings(apply_section_edits(outline, "blog", rows)) == _headings(outline)


def test_repeated_and_stale_ids_are_ignored():
    edited = apply_section_edits(
        _blog_outline(),
        "blog",
        [
            {"id": BLOG_IDS[1]},
            {"id": BLOG_IDS[1], "heading": "Second copy"},
            {"id": "structure.sections:7"},
            {"id": BLOG_IDS[0]},
        ],
    )

    assert _headings(edited) == ["Cushioning and support", "Why the right shoe matters"]


def test_a_flat_sections_list_is_reordered():
    outline = {"title": "T", "sections": [_section("One"), _section("Two"), _section("Three")]}

    edited = apply_section_edits(
        outline, "blog", [{"id": "sections:2"}, {"id": "sections:0"}, {"id": "sections:1"}]
    )

    assert _headings(edited, ("sections",)) == ["Three", "One", "Two"]


# --- the writer and the validator follow the approved order -------------------


def test_writer_plan_and_expected_headings_follow_the_order():
    rows = [
        {"id": BLOG_IDS[3], "heading": "Get fitted first"},
        {"id": BLOG_IDS[1]},
        {"id": BLOG_IDS[0]},
    ]
    edited = apply_section_edits(_blog_outline(), "blog", rows)

    expected = resolve_expected_headings(resolve_outline_structure(edited, "blog"))
    assert expected == ["Get fitted first", "Cushioning and support", "Why the right shoe matters"]

    plan = _format_outline_for_generation(edited, "blog")
    positions = [plan.index(heading) for heading in expected]
    assert positions == sorted(positions)
    assert "Heel drop explained" not in plan


# --- the gate ----------------------------------------------------------------


def _approve(monkeypatch, response):
    payloads = []

    def _interrupt(payload):
        payloads.append(payload)
        return response

    monkeypatch.setattr(review_module, "interrupt", _interrupt)
    state = {"content": {"outline": _blog_outline(), "content_type": "blog"}}
    result = review_module.review_outline(state)
    return payloads[0], result["content"]["outline"]


def test_gate_payload_carries_the_editable_sections(monkeypatch):
    payload, _ = _approve(monkeypatch, {"action": "approve"})

    assert [row["id"] for row in payload["editable_sections"]] == BLOG_IDS


def test_approval_without_sections_keeps_the_outline(monkeypatch):
    _, outline = _approve(monkeypatch, {"action": "approve"})

    assert _headings(outline) == _headings(_blog_outline())
    assert outline["_render"] == {"blocks": []}  # untouched when nothing was edited
    assert outline["status"] == "approved"


def test_approval_with_sections_writes_the_order_and_refreshes_the_display(monkeypatch):
    rows = [{"id": BLOG_IDS[2], "heading": "Heel drop, explained simply"}, {"id": BLOG_IDS[0]}]

    _, outline = _approve(monkeypatch, {"action": "approve", "sections": rows})

    assert _headings(outline) == ["Heel drop, explained simply", "Why the right shoe matters"]
    assert outline["status"] == "approved"
    rendered = repr(outline["_render"])
    assert "Heel drop, explained simply" in rendered
    assert "Cushioning and support" not in rendered
