"""Regression tests for comparison/best-tools brand slotting.

Two production defects are pinned here, both reported as "the article compares
Agency A with Agency B instead of real products":

1. The outline model, given no real product names, invented placeholder
   entities — and because a placeholder is a well-formed product dict, the
   brand-slot logic mistook it for a real competitor worth protecting and put
   the approved brand in the hero prose instead of in the comparison.
2. The comparison schema keyed every block (`feature_matrix`, `pricing`,
   verdict, recommendations) by SLOT POSITION, so any reordering silently
   re-pointed them at a different product — a competitor's pricing could end up
   published under the brand's name.

The tests below are written against behaviour a reader would notice, not
internal call sequences, so they stay meaningful if the implementation moves.
"""

from __future__ import annotations

import copy

import pytest

from src.flow.engines.content.generation.brand_slot import apply_brand_slot_to_outline
from src.flow.model.structure.outlines.product_names import (
    find_placeholder_names_in_text,
    is_placeholder_product_name,
)

PROMO = {
    "brand_name": "Rext",
    "brand_url": "https://rext.ai",
    "about": "AI SEO content platform",
    "selling_position": "Ship SEO content 10x faster",
}


def _comparison_outline(product_names: list[str], prices: list[str]) -> dict:
    """A comparison outline whose every block references products BY NAME."""
    return {
        "promote_brand": True,
        "brand_voice_promotion": copy.deepcopy(PROMO),
        "hero": {
            "headline": " vs ".join(product_names),
            "subheadline": "Which one should you pick?",
        },
        "products": [
            {
                "name": name,
                "description": f"{name} description",
                "strengths": [f"{name} strength"],
                "weaknesses": [f"{name} weakness"],
                "best_for": ["teams"],
            }
            for name in product_names
        ],
        "feature_matrix": {
            "products_compared": list(product_names),
            "rows": [{"feature": "Price", "values": list(prices)}],
        },
        "pricing": {
            "entries": [
                {"product_name": name, "price": price} for name, price in zip(product_names, prices)
            ],
            "value_analysis": "analysis",
        },
        "use_cases": {
            "comparisons": [
                {"use_case": "SMB", "best_choice": product_names[0], "reasoning": "why"}
            ]
        },
        "head_to_head": {
            "winner_overall": product_names[0],
            "best_for_beginners": product_names[0],
            "best_budget_option": product_names[-1],
        },
        "recommendations": {
            "recommendations": [
                {
                    "scenario": "Budget buyers",
                    "recommended_product": product_names[0],
                    "justification": "cheapest",
                }
            ]
        },
    }


def _matrix_value(outline: dict, product_name: str, row_index: int = 0) -> str:
    """The matrix value belonging to `product_name` — resolved through the column
    header, which is the only honest way to ask the question."""
    matrix = outline["feature_matrix"]
    index = matrix["products_compared"].index(product_name)
    return matrix["rows"][row_index]["values"][index]


def _product_names(outline: dict) -> list[str]:
    return [product["name"] for product in outline["products"]]


# ── placeholder detection ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    ["Agency A", "Agency B", "Tool 1", "Product One", "Option #2", "Your Brand", "Acme Corp", ""],
)
def test_placeholder_names_are_detected(name):
    assert is_placeholder_product_name(name) is True


@pytest.mark.parametrize(
    "name",
    ["Ahrefs", "Semrush", "HubSpot", "Zoho CRM", "Monday.com", "1Password", "Product Hunt"],
)
def test_real_product_names_are_not_flagged(name):
    """A false positive here would delete a real competitor from a comparison,
    which is worse than the placeholder the check is hunting."""
    assert is_placeholder_product_name(name) is False


def test_placeholder_detection_in_prose_ignores_ordinary_lowercase_english():
    assert find_placeholder_names_in_text("Agency A beat Agency B") == ["Agency A", "Agency B"]
    assert find_placeholder_names_in_text("pick the tool a beginner can learn") == []


# ── the reported bug: placeholder products ───────────────────────────────────


def test_placeholder_product_is_replaced_by_the_promoted_brand():
    """THE reported regression: 'Agency A vs Agency B' with the brand nowhere in
    the comparison. The brand must take a fake product's place, not the hero."""
    outline = _comparison_outline(["Agency A", "Agency B"], ["$100", "$200"])

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert _product_names(result)[0] == "Rext"
    assert "Agency A" not in _product_names(result)
    assert result["brand_voice_promotion"]["slot_block_keys"][0] == "products"


def test_evicted_placeholder_data_is_not_inherited_by_the_brand():
    """Everything the outline said about a fake company was invented, so it must
    leave with it — the brand must not inherit Agency A's $100 price."""
    outline = _comparison_outline(["Agency A", "Agency B"], ["$100", "$200"])

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert _matrix_value(result, "Rext") != "$100"
    assert "fill from brand info" in _matrix_value(result, "Rext")
    # The surviving product keeps its own value, still correctly aligned.
    assert _matrix_value(result, "Agency B") == "$200"
    prices = {entry["product_name"]: entry["price"] for entry in result["pricing"]["entries"]}
    assert prices["Agency B"] == "$200"
    assert "$100" not in prices.values()


def test_references_to_an_evicted_placeholder_are_neutralised_not_repointed():
    """A verdict naming a deleted fake must not silently become a verdict about
    the brand — that is the misattribution this rewrite exists to prevent."""
    outline = _comparison_outline(["Agency A", "Agency B"], ["$100", "$200"])

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert result["head_to_head"]["winner_overall"] == "tie"
    assert result["use_cases"]["comparisons"][0]["best_choice"] == "tie"
    recommended = [
        rec["recommended_product"] for rec in result["recommendations"]["recommendations"]
    ]
    assert "Agency A" not in recommended


def test_comparison_of_two_placeholders_keeps_a_second_product_to_compare_against():
    """Dropping every fake would leave a one-product 'comparison'."""
    outline = _comparison_outline(["Agency A", "Agency B"], ["$100", "$200"])

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert len(result["products"]) >= 2


# ── the cardinality bug: two real products ───────────────────────────────────


def test_brand_is_added_without_evicting_real_products():
    """Previously this fell back to the hero and the brand never appeared in the
    comparison at all, because both fixed slots were occupied."""
    outline = _comparison_outline(["Ahrefs", "Semrush"], ["$99", "$129"])

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert _product_names(result) == ["Rext", "Ahrefs", "Semrush"]


def test_real_products_keep_their_own_data_after_the_brand_is_inserted():
    """The positional-keying corruption: inserting at the front must not shift
    anyone else's pricing onto the wrong product."""
    outline = _comparison_outline(["Ahrefs", "Semrush"], ["$99", "$129"])

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert _matrix_value(result, "Ahrefs") == "$99"
    assert _matrix_value(result, "Semrush") == "$129"
    assert len(result["feature_matrix"]["rows"][0]["values"]) == len(
        result["feature_matrix"]["products_compared"]
    )


def test_approved_judgements_about_competitors_are_left_alone():
    """The reviewer approved 'Ahrefs wins overall'; slotting the brand in must
    not quietly overwrite that."""
    outline = _comparison_outline(["Ahrefs", "Semrush"], ["$99", "$129"])

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert result["head_to_head"]["winner_overall"] == "Ahrefs"
    assert result["use_cases"]["comparisons"][0]["best_choice"] == "Ahrefs"


def test_brand_reaches_the_blocks_a_reader_compares_on():
    """Being first in `products` is not being IN the comparison — the table,
    pricing and recommendations each carry their own list."""
    outline = _comparison_outline(["Ahrefs", "Semrush"], ["$99", "$129"])

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert "Rext" in result["feature_matrix"]["products_compared"]
    assert any(entry["product_name"] == "Rext" for entry in result["pricing"]["entries"])
    assert any(
        rec["recommended_product"] == "Rext" for rec in result["recommendations"]["recommendations"]
    )
    assert set(result["brand_voice_promotion"]["slot_block_keys"]) >= {
        "products",
        "feature_matrix",
        "pricing",
        "recommendations",
    }


def test_brand_already_compared_is_promoted_without_duplication():
    outline = _comparison_outline(["Ahrefs", "Rext", "Semrush"], ["$99", "$49", "$129"])

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert _product_names(result)[0] == "Rext"
    assert _product_names(result).count("Rext") == 1
    # Its own approved value follows it, rather than being replaced by a marker.
    assert _matrix_value(result, "Rext") == "$49"


def test_slotting_is_idempotent():
    """Re-approval (or a checkpoint replay) must not stack duplicate entries."""
    outline = _comparison_outline(["Ahrefs", "Semrush"], ["$99", "$129"])

    once = apply_brand_slot_to_outline(outline, "comparison")
    twice = apply_brand_slot_to_outline(once, "comparison")

    assert _product_names(twice) == _product_names(once)
    assert len(twice["pricing"]["entries"]) == len(once["pricing"]["entries"])
    assert len(twice["recommendations"]["recommendations"]) == len(
        once["recommendations"]["recommendations"]
    )


# ── backward compatibility ───────────────────────────────────────────────────


def test_legacy_product_a_product_b_outline_still_works():
    """Outlines approved before the migration sit in LangGraph checkpoints in the
    old two-slot shape and must still flow through generation."""
    outline = _comparison_outline(["Ahrefs", "Semrush"], ["$99", "$129"])
    outline["products"] = {
        "product_a": {"name": "Ahrefs"},
        "product_b": {"name": "Semrush"},
    }

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert isinstance(result["products"], list)
    assert _product_names(result) == ["Rext", "Ahrefs", "Semrush"]


def test_outline_without_products_is_left_unchanged():
    """Soft-fail contract: an unexpected shape must never corrupt the outline."""
    outline = {
        "promote_brand": True,
        "brand_voice_promotion": copy.deepcopy(PROMO),
        "hero": {"headline": "h", "subheadline": "s"},
    }

    result = apply_brand_slot_to_outline(outline, "comparison")

    assert "products" not in result


# ── best-tools ───────────────────────────────────────────────────────────────


def _best_tools_outline() -> dict:
    return {
        "promote_brand": True,
        "brand_voice_promotion": copy.deepcopy(PROMO),
        "hero": {"headline": "Best SEO tools", "subheadline": "How we picked"},
        "rankings": [
            {
                "category": "SEO tools",
                "ranked_tools": [
                    {
                        "rank": 1,
                        "tool": {"name": "Ahrefs", "description": "d"},
                        "ranking_reason": "r",
                    },
                    {
                        "rank": 2,
                        "tool": {"name": "Semrush", "description": "d"},
                        "ranking_reason": "r",
                    },
                ],
            }
        ],
        "comparison_matrix": {
            "tools_compared": ["Ahrefs", "Semrush"],
            "rows": [{"feature": "Price", "tool_values": ["$99", "$129"]}],
        },
        "categories": {
            "categories": [
                {
                    "name": "Content and SEO platforms",
                    "description": "AI SEO content platforms",
                    "tools": ["Ahrefs"],
                },
                {"name": "Link building", "description": "backlinks", "tools": ["Semrush"]},
            ]
        },
        "use_cases": {"matches": [{"use_case": "Backlinks", "best_tool": "Ahrefs", "reason": "r"}]},
        "pricing_insights": [
            {"tool_name": "Ahrefs", "pricing_summary": "$99", "value_assessment": "v"}
        ],
        "decision_guide": {
            "best_for_beginners": "Semrush",
            "best_for_professionals": "Ahrefs",
            "best_budget_option": "Semrush",
            "best_premium_option": "Ahrefs",
            "best_overall": "Ahrefs",
        },
    }


def test_best_tools_brand_is_ranked_first_and_reaches_every_name_keyed_block():
    result = apply_brand_slot_to_outline(_best_tools_outline(), "best-tools")

    ranked = result["rankings"][0]["ranked_tools"]
    assert ranked[0]["tool"]["name"] == "Rext"
    assert [entry["rank"] for entry in ranked] == [1, 2, 3]
    assert result["comparison_matrix"]["tools_compared"][0] == "Rext"
    assert result["decision_guide"]["best_overall"] == "Rext"
    assert result["pricing_insights"][0]["tool_name"] == "Rext"
    assert any(match["best_tool"] == "Rext" for match in result["use_cases"]["matches"])
    assert any("Rext" in group["tools"] for group in result["categories"]["categories"])


def test_best_tools_matrix_values_stay_with_their_tool():
    result = apply_brand_slot_to_outline(_best_tools_outline(), "best-tools")

    matrix = result["comparison_matrix"]
    values = matrix["rows"][0]["tool_values"]
    assert len(values) == len(matrix["tools_compared"])
    assert values[matrix["tools_compared"].index("Ahrefs")] == "$99"
    assert values[matrix["tools_compared"].index("Semrush")] == "$129"


def test_best_tools_does_not_reassign_a_competitors_approved_use_case():
    """Existing matches are approved judgements about other tools; the brand is
    appended alongside them rather than taking one over."""
    result = apply_brand_slot_to_outline(_best_tools_outline(), "best-tools")

    matches = result["use_cases"]["matches"]
    assert matches[0] == {"use_case": "Backlinks", "best_tool": "Ahrefs", "reason": "r"}


def test_best_tools_brand_is_filed_under_the_most_relevant_category():
    result = apply_brand_slot_to_outline(_best_tools_outline(), "best-tools")

    groups = {group["name"]: group["tools"] for group in result["categories"]["categories"]}
    assert "Rext" in groups["Content and SEO platforms"]
    assert "Rext" not in groups["Link building"]
