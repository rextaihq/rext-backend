"""The outline gate lists every part of the article, in order (revnix/rext-control#814).

A product roundup's review step showed its alternatives alone: the picks the
article reviews sit two levels down in the outline, so the gate had no rows for
them. `structure` lists each part the body is built from: a list the reviewer
may edit by its path, any other part with what it covers, to read.
"""

import json

import pytest

import src.flow.engines.content.review.outline as review_module
import src.flow.engines.content.review.outline_parts as parts_module
from src.flow.engines.content.generation.outline_structure import resolve_outline_structure
from src.flow.engines.content.generation.structured_body import (
    build_structured_content_model,
    typed_section_blocks,
)
from src.flow.engines.content.review.outline_edits import editable_sections
from src.flow.engines.content.review.outline_parts import (
    MAX_ITEMS,
    MAX_POINT_LENGTH,
    MAX_POINTS,
    gate_structure,
    safe_gate_structure,
)
from src.flow.model.structure.contents import get_generated_content_model


def _product(name, best_for):
    return {
        "name": name,
        "description": f"{name} boils fast.",
        "key_features": ["Auto shut-off"],
        "pros": ["Quiet"],
        "cons": ["Small"],
        "pricing_model": "One-time",
        "starting_price": "Approx. $39",
        "best_for": best_for,
        "rating_score": 8.5,
        "affiliate_link": "https://shop.example/kettle",
    }


def _roundup_outline():
    return {
        "title": "Best budget kettles",
        "hero": {"headline": "Best budget kettles", "subheadline": "Tested at home."},
        "methodology": {
            "criteria": ["Boil time", "Noise"],
            "testing_process": "Each kettle boiled a litre ten times.",
            "update_frequency": "Yearly",
            "editorial_policy": "No paid placements.",
        },
        "best_picks": {
            "groups": [
                {
                    "group_name": "Best overall",
                    "description": "The ones most kitchens should buy.",
                    "products": [
                        {
                            "rank": 1,
                            "product": _product("Quick Kettle", ["Families", "Tea drinkers"]),
                            "reason_for_rank": "Fastest boil of the test.",
                        },
                        {
                            "rank": 2,
                            "product": _product("Small Kettle", ["One cup"]),
                            "reason_for_rank": "Takes the least room.",
                        },
                    ],
                },
                {
                    "group_name": "Best for travel",
                    "description": "Light enough for a bag.",
                    "products": [
                        {
                            "rank": 1,
                            "product": _product("Fold Kettle", []),
                            "reason_for_rank": "Folds flat.",
                        }
                    ],
                },
            ]
        },
        "use_cases": {
            "matches": [
                {
                    "use_case": "A shared office",
                    "recommended_product": "Quick Kettle",
                    "reasoning": "It refills fast.",
                }
            ]
        },
        "decision_guide": {
            "best_overall": "Quick Kettle",
            "best_budget": "Small Kettle",
            "best_premium": "Quick Kettle",
            "best_for_beginners": "Small Kettle",
            "best_for_advanced_users": "Quick Kettle",
        },
        "comparison_matrix": {
            "products": ["Quick Kettle", "Small Kettle"],
            "rows": [
                {"feature": "Boil time", "values": ["2 min 10 s", "3 min"]},
                {"feature": "Starting price", "values": ["Approx. $39", "Approx. $25"]},
            ],
        },
        "pricing": [
            {"product_name": "Quick Kettle", "price_range": "$35-45", "value_assessment": "good"},
            {"product_name": "Small Kettle", "price_range": "$20-30", "value_assessment": "good"},
        ],
        "alternatives": {
            "alternatives": [
                {"name": "Tall Kettle", "reason_to_consider": "A step up."},
                {"name": "Slow Kettle", "reason_to_consider": "Quieter."},
            ]
        },
        "social_proof": {
            "user_reviews_summary": ["Owners praise the quiet boil."],
            "expert_opinions": ["Reviewers like the lid."],
            "adoption_metrics": ["Sold 2 million units in 2025"],
        },
        "faqs": {"faqs": [{"question": "How long does a kettle last?", "answer": "Years."}]},
        "cta": {"primary_cta": "Compare the picks", "secondary_cta": None},
        "_render": {"blocks": []},
    }


def _tools_outline():
    def tool(name):
        return {
            "name": name,
            "description": f"{name} plans beds.",
            "key_features": ["Templates"],
            "pros": ["Free tier"],
            "cons": ["No app"],
            "pricing_model": "Subscription",
            "starting_price": "$9",
            "best_for": ["Allotments"],
            "rating_score": 9.1,
            "link": "https://tools.example/",
        }

    return {
        "title": "Best garden planners",
        "hero": {"headline": "Best garden planners", "subheadline": "For small plots."},
        "selection_criteria": {
            "criteria": ["Ease of use"],
            "evaluation_method": "A season of use.",
            "update_frequency": "Quarterly",
        },
        "rankings": [
            {
                "category": "Best planners",
                "ranked_tools": [
                    {"rank": 1, "tool": tool("Bedplan"), "ranking_reason": "Easiest to start."},
                    {"rank": 2, "tool": tool("Plotwise"), "ranking_reason": "Best for rotation."},
                ],
            }
        ],
        "categories": {
            "categories": [
                {"name": "Free planners", "description": "No card needed.", "tools": ["Bedplan"]}
            ]
        },
        "update_info": {"last_updated": "2023-10-01", "frequency_of_updates": "Quarterly"},
        "faqs": {"faqs": [{"question": "Is a planner worth it?", "answer": "Often."}]},
        "cta": {"primary_cta": "Try a planner"},
    }


def _blog_outline():
    return {
        "title": "Running shoes for beginners",
        "hero": {"headline": "Running shoes for beginners", "subheadline": "How to choose."},
        "structure": {
            "sections": [
                {"heading": "Why the right shoe matters", "heading_level": "H2", "key_points": []},
                {"heading": "How to get fitted", "heading_level": "H2", "key_points": []},
            ]
        },
        "faqs": {"faqs": [{"question": "How often should I replace them?", "answer": "Often."}]},
    }


def _how_to_outline():
    return {
        "title": "How to descale a kettle",
        "hero": {"headline": "How to descale a kettle", "subheadline": "In ten minutes."},
        "steps": {
            "steps": [
                {"title": "Fill it with vinegar and water", "description": "Half and half."},
                {"title": "Boil and rinse", "description": "Twice."},
            ]
        },
        "tools": {"tools": [{"name": "White vinegar", "purpose": "Dissolves the scale."}]},
    }


OUTLINES = [
    ("product-roundup", _roundup_outline),
    ("best-tools", _tools_outline),
    ("blog", _blog_outline),
    ("how-to-guide", _how_to_outline),
]


def _part(parts, key):
    return next(part for part in parts if part["key"] == key)


def test_a_roundup_lists_its_parts_in_the_order_the_article_is_written():
    parts = gate_structure(_roundup_outline(), "product-roundup")

    assert [part["key"] for part in parts] == [
        "methodology",
        "best_picks",
        "use_cases",
        "decision_guide",
        "comparison_matrix",
        "pricing",
        "alternatives",
        "social_proof",
    ]


def test_the_picks_are_the_products_the_article_reviews():
    picks = _part(gate_structure(_roundup_outline(), "product-roundup"), "best_picks")

    assert picks["heading"] == "Best Picks"
    assert picks["items"] == [
        {
            "label": "Quick Kettle",
            "points": [
                "Best overall",
                "Fastest boil of the test.",
                "Best for: Families, Tea drinkers",
            ],
        },
        {
            "label": "Small Kettle",
            "points": ["Best overall", "Takes the least room.", "Best for: One cup"],
        },
        {"label": "Fold Kettle", "points": ["Best for travel", "Folds flat."]},
    ]


def test_best_tools_lists_its_ranked_tools():
    rankings = _part(gate_structure(_tools_outline(), "best-tools"), "rankings")

    assert [item["label"] for item in rankings["items"]] == ["Bedplan", "Plotwise"]
    assert rankings["items"][0]["points"][:2] == ["Best planners", "Easiest to start."]


def test_the_list_a_reviewer_edits_keeps_its_place_and_names_its_rows():
    outline = _roundup_outline()
    alternatives = _part(gate_structure(outline, "product-roundup"), "alternatives")

    assert alternatives == {
        "key": "alternatives",
        "heading": "Alternatives",
        "list": "alternatives.alternatives",
    }
    assert {row["list"] for row in editable_sections(outline, "product-roundup")} == {
        "alternatives.alternatives"
    }


@pytest.mark.parametrize("content_type, build", OUTLINES)
def test_every_list_the_gate_offers_rows_for_has_its_part(content_type, build):
    outline = build()
    offered = {row["list"] for row in editable_sections(outline, content_type)}
    listed = {part["list"] for part in gate_structure(outline, content_type) if "list" in part}

    assert listed == offered
    # A part is a list to edit or something to read, never both and never neither.
    for part in gate_structure(outline, content_type):
        assert ("list" in part) != bool(part.get("items"))


@pytest.mark.parametrize("content_type, build", OUTLINES)
def test_the_hero_the_faq_and_the_call_to_action_are_no_parts(content_type, build):
    keys = {part["key"] for part in gate_structure(build(), content_type)}

    assert not keys & {"hero", "faq", "faqs", "cta", "final_cta"}


def test_a_blog_is_its_one_list_of_sections():
    assert gate_structure(_blog_outline(), "blog") == [
        {"key": "structure", "heading": "Structure", "list": "structure.sections"}
    ]


def test_a_how_to_keeps_the_steps_a_typed_field_writes():
    parts = gate_structure(_how_to_outline(), "how-to-guide")

    assert _part(parts, "steps")["list"] == "steps.steps"
    assert _part(parts, "tools")["list"] == "tools.tools"


@pytest.mark.parametrize("content_type, build", OUTLINES)
def test_no_price_rating_date_or_link_is_shown(content_type, build):
    shown = json.dumps(gate_structure(build(), content_type))

    for fact in ("$", "8.5", "9.1", "https://", "2 million", "2023-10-01", "2 min 10 s"):
        assert fact not in shown
    # What a part covers stays: the table's rows by name, the pricing's products.
    if content_type == "product-roundup":
        parts = gate_structure(build(), content_type)
        assert [item["label"] for item in _part(parts, "comparison_matrix")["items"]] == [
            "Boil time",
            "Starting price",
        ]
        assert [item["label"] for item in _part(parts, "pricing")["items"]] == [
            "Quick Kettle",
            "Small Kettle",
        ]
        assert _part(parts, "social_proof")["items"][0]["points"] == [
            "Owners praise the quiet boil."
        ]


def test_a_part_shows_a_bounded_amount():
    outline = _roundup_outline()
    outline["use_cases"]["matches"] = [
        {
            "use_case": f"Use case {number}",
            "recommended_product": "Quick Kettle",
            "reasoning": "It refills fast, " + "and it stays quiet while it does " * 8,
            "note": "A fourth thing to say.",
            "another": "A fifth thing to say.",
        }
        for number in range(MAX_ITEMS + 10)
    ]
    items = _part(gate_structure(outline, "product-roundup"), "use_cases")["items"]

    assert len(items) == MAX_ITEMS
    for item in items:
        assert len(item["points"]) <= MAX_POINTS
        assert all(len(point) <= MAX_POINT_LENGTH for point in item["points"])
    assert items[0]["points"][1].endswith("…")


def test_a_part_with_nothing_to_read_is_left_out():
    outline = _roundup_outline()
    outline["pricing"] = [{"price_range": "$35-45"}]

    assert "pricing" not in {part["key"] for part in gate_structure(outline, "product-roundup")}


@pytest.mark.parametrize("content_type, build", OUTLINES)
def test_the_parts_left_to_typed_fields_are_the_ones_the_writers_model_leaves(content_type, build):
    """`_typed_fields` and structured_body's collision filter read one set from one model."""
    outline = build()
    base = get_generated_content_model(content_type)
    resolved = resolve_outline_structure(outline, content_type)
    derived = build_structured_content_model(outline, content_type, base, blocks=list(resolved))
    assert derived is not None
    written = {block.parent or block.key for block in derived[1]}
    left_to_typed_fields = {block.key for block in resolved} - written - {"faq", "faqs"}

    assert left_to_typed_fields == {
        block.key for block in resolved if block.key in parts_module._typed_fields(content_type)
    }
    # A typed field's section the article shows is a part; any other is not, unless the gate
    # offers its rows.
    typed = {block.key for block in typed_section_blocks(outline, content_type)}
    offered = {row["list"].split(".")[0] for row in editable_sections(outline, content_type)}
    parts = {part["key"] for part in gate_structure(outline, content_type)}
    assert not (left_to_typed_fields - typed - offered) & parts


# --- the gate ----------------------------------------------------------------


def _gate(monkeypatch, outline, content_type):
    payloads = []

    def _interrupt(payload):
        payloads.append(payload)
        return {"action": "approve"}

    monkeypatch.setattr(review_module, "interrupt", _interrupt)
    review_module.review_outline({"content": {"outline": outline, "content_type": content_type}})
    return payloads[0]


def test_the_gate_payload_carries_the_structure(monkeypatch):
    payload = _gate(monkeypatch, _roundup_outline(), "product-roundup")

    assert payload["structure"] == gate_structure(_roundup_outline(), "product-roundup")
    assert [row["heading"] for row in payload["editable_sections"]] == [
        "Tall Kettle",
        "Slow Kettle",
    ]


def test_an_error_listing_the_parts_never_fails_the_gate(monkeypatch):
    def _broken(outline, content_type):
        raise ValueError("a shape nobody expected")

    monkeypatch.setattr(parts_module, "gate_structure", _broken)

    assert safe_gate_structure(_roundup_outline(), "product-roundup") == []
    payload = _gate(monkeypatch, _roundup_outline(), "product-roundup")
    assert payload["structure"] == []
    assert len(payload["editable_sections"]) == 2
