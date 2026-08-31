"""Coverage for the outline brand-slot writer.

The writer mutates a user-approved artifact, so the tests below care as much
about what it must NOT do (drop an approved product, add a top-level key,
duplicate an existing entry, raise on a malformed outline) as about where it
puts the brand.
"""

import pytest

from src.flow.engines.content.generation.brand_slot import apply_brand_slot_to_outline

PROMO = {
    "brand_name": "Acme",
    "brand_url": "https://acme.com",
    "about": "Acme is a project-management tool for remote teams.",
    "selling_position": "cuts onboarding time in half with automated workflows",
}


def _outline(**blocks):
    return {"promote_brand": True, "brand_voice_promotion": PROMO, **blocks}


@pytest.mark.unit
class TestRankedListTypes:
    def test_best_tools_inserts_first_and_renumbers(self):
        outline = _outline(rankings=[{"category": "CRM", "ranked_tools": [
            {"rank": 1, "tool": {"name": "Rival"}, "ranking_reason": "x"},
            {"rank": 2, "tool": {"name": "Other"}, "ranking_reason": "y"},
        ]}])
        result = apply_brand_slot_to_outline(outline, "best-tools")
        tools = result["rankings"][0]["ranked_tools"]
        assert [t["tool"]["name"] for t in tools] == ["Acme", "Rival", "Other"]
        assert [t["rank"] for t in tools] == [1, 2, 3]

    def test_existing_brand_entry_is_moved_not_duplicated(self):
        """The outline generator may already have included the brand. Inserting
        a second entry would produce a list that names it twice."""
        outline = _outline(rankings=[{"category": "CRM", "ranked_tools": [
            {"rank": 1, "tool": {"name": "Rival"}, "ranking_reason": "x"},
            {"rank": 2, "tool": {"name": "Acme"}, "ranking_reason": "y"},
        ]}])
        result = apply_brand_slot_to_outline(outline, "best-tools")
        names = [t["tool"]["name"] for t in result["rankings"][0]["ranked_tools"]]
        assert names == ["Acme", "Rival"]

    def test_product_roundup_leads_the_first_group(self):
        outline = _outline(best_picks={"groups": [{
            "group_name": "Best Overall", "description": "d",
            "products": [{"rank": 1, "product": {"name": "Rival"}, "reason_for_rank": "r"}],
        }]})
        result = apply_brand_slot_to_outline(outline, "product-roundup")
        products = result["best_picks"]["groups"][0]["products"]
        assert [p["product"]["name"] for p in products] == ["Acme", "Rival"]


@pytest.mark.unit
class TestComparison:
    def test_takes_product_a_when_a_slot_is_free(self):
        outline = _outline(
            hero={"headline": "Rival vs ?", "subheadline": "s"},
            products={"product_a": {"name": "Rival"}, "product_b": None},
        )
        result = apply_brand_slot_to_outline(outline, "comparison")
        assert result["products"]["product_a"]["name"] == "Acme"
        assert result["products"]["product_b"]["name"] == "Rival"

    def test_never_evicts_an_approved_product_when_both_slots_are_full(self):
        """ComparedProducts holds exactly two. Taking one for the brand would
        delete a product the article's title and feature matrix still reference —
        a worse defect than a late mention. The brand goes to the hero instead."""
        outline = _outline(
            hero={"headline": "Rival vs Other", "subheadline": "Which to pick"},
            products={"product_a": {"name": "Rival"}, "product_b": {"name": "Other"}},
        )
        result = apply_brand_slot_to_outline(outline, "comparison")
        assert result["products"]["product_a"]["name"] == "Rival"
        assert result["products"]["product_b"]["name"] == "Other"
        assert "Acme" in result["hero"]["subheadline"]

    def test_brand_already_in_product_b_is_promoted_to_product_a(self):
        outline = _outline(products={
            "product_a": {"name": "Rival"}, "product_b": {"name": "Acme"},
        })
        result = apply_brand_slot_to_outline(outline, "comparison")
        assert result["products"]["product_a"]["name"] == "Acme"
        assert result["products"]["product_b"]["name"] == "Rival"


@pytest.mark.unit
class TestAlternatives:
    def test_brand_goes_to_positioning_and_hero_not_competitors(self):
        """`alternatives_list.competitors` is the competitor set — filing our own
        product under it is semantically wrong, and the old prompt instruction
        told the model to do exactly that."""
        outline = _outline(
            differentiation={"unique_advantages": [], "key_differences": [], "positioning_statement": "generic"},
            hero={"headline": "Best alternatives to Rival", "subheadline": "For teams switching"},
            alternatives_list={"competitors": [{"name": "Rival"}]},
        )
        result = apply_brand_slot_to_outline(outline, "alternatives")
        assert "Acme" in result["differentiation"]["positioning_statement"]
        assert "Acme" in result["hero"]["subheadline"]
        assert [c["name"] for c in result["alternatives_list"]["competitors"]] == ["Rival"]


@pytest.mark.unit
class TestHeroPageTypes:
    @pytest.mark.parametrize("content_type", ["landing-page", "sales-page", "brand-page"])
    def test_prefers_top_types_get_the_brand_into_the_hero(self, content_type):
        outline = _outline(hero={"headline": "Ship faster", "subheadline": "Built for teams"})
        result = apply_brand_slot_to_outline(outline, content_type)
        assert "Acme" in result["hero"]["subheadline"]

    def test_headline_is_left_alone(self):
        """The headline carries the page's search intent; mangling it costs more
        than it gains, so the brand is appended to the subheadline instead."""
        outline = _outline(hero={"headline": "Ship faster", "subheadline": "Built for teams"})
        result = apply_brand_slot_to_outline(outline, "landing-page")
        assert result["hero"]["headline"] == "Ship faster"

    def test_hero_already_naming_the_brand_is_left_untouched(self):
        outline = _outline(hero={"headline": "Acme ships faster", "subheadline": "Built for teams"})
        result = apply_brand_slot_to_outline(outline, "landing-page")
        assert result["hero"]["subheadline"] == "Built for teams"


@pytest.mark.unit
class TestBodyOnlyTypes:
    SECTIONS = [
        {"heading": "What is onboarding", "purpose": "define", "key_points": ["basics"]},
        {"heading": "Automating onboarding workflows for remote teams", "purpose": "tools",
         "key_points": ["automation"]},
        {"heading": "Costs", "purpose": "money", "key_points": ["budget"]},
        {"heading": "Conclusion", "purpose": "wrap", "key_points": ["recap"]},
    ]

    def test_picks_the_relevant_section_inside_the_attention_window(self):
        outline = _outline(structure={"sections": [dict(s) for s in self.SECTIONS]})
        result = apply_brand_slot_to_outline(outline, "blog")
        sections = result["structure"]["sections"]
        assert any("Acme" in p for p in sections[1]["key_points"])
        # and nowhere else
        for idx in (0, 2, 3):
            assert not any("Acme" in p for p in sections[idx]["key_points"])

    def test_never_lands_in_the_back_half(self):
        """The whole point: a mention readers never reach is a wasted promotion."""
        outline = _outline(structure={"sections": [dict(s) for s in self.SECTIONS]})
        result = apply_brand_slot_to_outline(outline, "blog")
        sections = result["structure"]["sections"]
        placed_at = next(
            i for i, s in enumerate(sections) if any("Acme" in p for p in s["key_points"])
        )
        assert placed_at < len(sections) / 2

    def test_flat_top_level_sections_list_is_honoured(self):
        outline = _outline(sections=[dict(s) for s in self.SECTIONS])
        result = apply_brand_slot_to_outline(outline, "blog")
        assert any(
            any("Acme" in p for p in s["key_points"]) for s in result["sections"]
        )


@pytest.mark.unit
class TestSafety:
    def test_never_adds_a_top_level_key(self):
        """resolve_outline_structure turns an unknown top-level key into a
        REQUIRED heading, so a stray key here would manufacture a phantom section
        no article ever contains and fail check_required_sections forever."""
        outline = _outline(structure={"sections": [
            {"heading": "H", "purpose": "p", "key_points": ["k"]},
        ]})
        result = apply_brand_slot_to_outline(outline, "blog")
        assert set(result) == set(outline)

    def test_does_not_mutate_the_input(self):
        outline = _outline(rankings=[{"category": "CRM", "ranked_tools": [
            {"rank": 1, "tool": {"name": "Rival"}, "ranking_reason": "x"},
        ]}])
        apply_brand_slot_to_outline(outline, "best-tools")
        assert [t["tool"]["name"] for t in outline["rankings"][0]["ranked_tools"]] == ["Rival"]

    @pytest.mark.parametrize("outline,content_type", [
        ({}, "blog"),
        ({"brand_voice_promotion": {}}, "blog"),
        ({"brand_voice_promotion": PROMO, "rankings": "nonsense"}, "best-tools"),
        ({"brand_voice_promotion": PROMO, "rankings": []}, "best-tools"),
        ({"brand_voice_promotion": PROMO, "structure": {"sections": []}}, "blog"),
        ({"brand_voice_promotion": PROMO}, "some-unknown-type"),
    ])
    def test_malformed_outline_is_a_clean_no_op(self, outline, content_type):
        """The approved outline is never re-validated through Pydantic, so a bad
        write raises nothing and silently corrupts. Degrading to the previous
        prompt-only behaviour is the correct failure mode; raising here would
        break outline approval outright."""
        assert apply_brand_slot_to_outline(outline, content_type) == outline

    def test_non_dict_input_is_returned_untouched(self):
        assert apply_brand_slot_to_outline(None, "blog") is None
