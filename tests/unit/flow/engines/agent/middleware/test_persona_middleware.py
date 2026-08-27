"""Unit tests for PersonaInjectionMiddleware's outline/brand-placement rendering.

Covers a real, critical bug: _build_outline_block() (the SYSTEM prompt, read
first and treated as authoritative) only ever rendered a flat `sections`
list — the exact same gap already fixed in content_generation.py's human
message. For every content type without a flat sections list (best-tools,
landing-page, comparison, brand-page, ...), the system prompt showed ZERO
structural plan, while the human message (fixed separately) showed the real
one — the model was getting two contradictory pictures of the article's
structure, and the system prompt never mentioned brand-placement rules at
all. Both are fixed here.
"""

import pytest

from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware


@pytest.fixture
def middleware():
    return PersonaInjectionMiddleware()


@pytest.mark.unit
class TestBuildOutlineBlockStructuralPlan:
    def test_flat_sections_schema_still_renders_sections(self, middleware):
        outline = {
            "title": "How to X",
            "sections": [{"heading": "Step 1", "key_points": ["do this"]}],
        }
        rendered = middleware._build_outline_block(outline, "how-to-guide")
        assert "Sections:" in rendered
        assert "Step 1" in rendered
        # Must NOT fall into the structural-plan fallback when real sections exist
        assert "Structural Plan" not in rendered

    def test_ranked_list_schema_renders_structural_plan_from_render_blocks(self, middleware):
        """The actual bug: a best-tools outline with no flat `sections` used
        to produce a system prompt with NO structure at all beyond
        title/brief/tone/keywords."""
        outline = {
            "title": "Best Project Management Tools",
            "rankings": {
                "ranked_tools": [
                    {"tool_name": "Tool Alpha", "key_features": ["fast", "cheap"]},
                    {"tool_name": "Tool Beta", "key_features": ["scalable"]},
                ]
            },
        }
        rendered = middleware._build_outline_block(outline, "best-tools")
        assert "Structural Plan" in rendered
        assert "Rankings" in rendered
        assert "Tool Alpha" in rendered
        assert "Tool Beta" in rendered
        assert "fast" in rendered

    def test_hero_led_schema_renders_hero_block_and_conversion_goal(self, middleware):
        outline = {
            "title": "Acme Landing Page",
            "conversion_goal": "Start Trial",
            "hero": {
                "headline": "Ship faster",
                "subheadline": "Automate the busywork",
                "primary_cta": "Start Trial",
            },
            "problem": {"pain_points": ["Manual busywork"]},
        }
        rendered = middleware._build_outline_block(outline, "landing-page")
        assert "## Hero" in rendered
        assert rendered.index("## Hero") < rendered.index("## Problem")
        assert "Ship faster" in rendered
        assert "Automate the busywork" in rendered
        assert "Conversion goal: Start Trial" in rendered

    def test_system_prompt_and_human_message_describe_one_structure(self, middleware):
        """Both prompts resolve from the same function, so they can no longer
        show the model two contradictory pictures of the article."""
        from src.flow.engines.content.generation.content_generation import (
            _format_outline_for_generation,
        )

        outline = {
            "title": "Acme Landing Page",
            "hero": {"headline": "Ship faster"},
            "problem": {"pain_points": ["Manual busywork"]},
            "social_proof": {"metrics": ["10,000+ users"]},
        }
        system = middleware._build_outline_block(outline, "landing-page")
        human = _format_outline_for_generation(outline, "landing-page")
        for heading in ("## Hero", "## Problem", "## Social Proof"):
            assert heading in system and heading in human


@pytest.mark.unit
class TestBuildBrandPlacementBlock:
    BRAND_PROMO = {"brand_name": "Acme", "brand_url": "https://acme.com"}

    def test_no_promotion_returns_empty(self, middleware):
        outline = {"promote_brand": False}
        assert middleware._build_brand_placement_block(outline, "best-tools") == ""

    def test_no_outline_returns_empty(self, middleware):
        assert middleware._build_brand_placement_block(None, "best-tools") == ""

    def test_promotion_without_brand_name_returns_empty(self, middleware):
        outline = {"promote_brand": True, "brand_voice_promotion": {"brand_name": ""}}
        assert middleware._build_brand_placement_block(outline, "best-tools") == ""

    def test_promoted_brand_produces_mandatory_override_block(self, middleware):
        outline = {"promote_brand": True, "brand_voice_promotion": self.BRAND_PROMO}
        rendered = middleware._build_brand_placement_block(outline, "landing-page")
        assert "MANDATORY" in rendered
        assert "OVERRIDES GENERIC OUTLINE GUIDANCE" in rendered
        assert "Acme" in rendered
        assert "PLACEMENT REQUIREMENT" in rendered

    def test_featured_content_type_points_at_the_reserved_slot(self, middleware):
        """brand_slot.apply_brand_slot_to_outline now reserves the position in
        the outline at approval time, so the prompt tells the model to honour the
        slot the Structural Plan already shows rather than to invent one."""
        outline = {"promote_brand": True, "brand_voice_promotion": self.BRAND_PROMO}
        rendered = middleware._build_brand_placement_block(outline, "best-tools")
        assert "STRUCTURAL REQUIREMENT" in rendered
        assert "Rankings list" in rendered
        assert "already places" in rendered.lower()

    def test_hero_content_type_gets_an_above_the_fold_structural_instruction(self, middleware):
        """Previously landing-page got only descriptive placement prose, which a
        model can satisfy with generic value-prop copy that never names the
        brand — so the mention kept ending up at the bottom of the page."""
        outline = {"promote_brand": True, "brand_voice_promotion": self.BRAND_PROMO}
        rendered = middleware._build_brand_placement_block(outline, "landing-page")
        assert "STRUCTURAL EDIT REQUIRED" in rendered
        assert "Acme" in rendered

    def test_body_only_content_type_has_no_structural_edit_instruction(self, middleware):
        """A blog's mention belongs mid-body — there is no structural "top" to
        anchor it to, so the placement prose alone is unambiguous."""
        outline = {"promote_brand": True, "brand_voice_promotion": self.BRAND_PROMO}
        rendered = middleware._build_brand_placement_block(outline, "blog")
        assert "STRUCTURAL EDIT REQUIRED" not in rendered

    def test_final_verification_line_present(self, middleware):
        outline = {"promote_brand": True, "brand_voice_promotion": self.BRAND_PROMO}
        rendered = middleware._build_brand_placement_block(outline, "brand-page")
        assert "Before submitting" in rendered
        assert "WRONG position" in rendered


@pytest.mark.unit
class TestFullSystemPromptWiring:
    """End-to-end: the block actually lands in the assembled system prompt,
    in the right relative position (after the outline block, before the
    generic content instructions that could otherwise read as license to
    deprioritize it)."""

    def test_brand_block_appears_in_full_prompt_when_promoted(self, middleware):
        outline = {
            "title": "Best Project Management Tools",
            "promote_brand": True,
            "brand_voice_promotion": {"brand_name": "Acme", "brand_url": "https://acme.com"},
            "rankings": {"ranked_tools": [{"tool_name": "Tool Alpha"}]},
        }
        full_prompt = middleware._build_full_content_prompt(None, outline, 2000, "best-tools")
        assert "PRODUCT-LED MENTION" in full_prompt
        assert "Acme" in full_prompt
        outline_idx = full_prompt.index("Approved Content Outline")
        brand_idx = full_prompt.index("PRODUCT-LED MENTION")
        instructions_idx = full_prompt.index("WHY THIS KEEPS GETTING FLAGGED AS AI")
        assert outline_idx < brand_idx < instructions_idx

    def test_no_brand_block_when_not_promoted(self, middleware):
        """"PRODUCT-LED MENTION" itself still appears in the static
        CONTENT_INSTRUCTIONS (the fabrication-rules section references it
        generically) — the thing that must NOT appear is the mandatory
        override heading this block specifically adds."""
        outline = {"title": "A Blog Post", "promote_brand": False}
        full_prompt = middleware._build_full_content_prompt(None, outline, 2000, "blog")
        assert "OVERRIDES GENERIC OUTLINE GUIDANCE" not in full_prompt
        assert "PLACEMENT REQUIREMENT FOR THIS CONTENT TYPE" not in full_prompt
