import pytest


def _base_common(content_type: str):
    return {
        "content_type": content_type,
        "title": f"{content_type} focus keyphrase",
        "slug_suggestion": "focus-keyphrase",
        "brief": "Clear value prop for the reader.",
        "focus_keyphrase": "focus keyphrase",
        "keywords_to_include": ["secondary keyword"],
        "target_audience": ["Beginners"],
        "tone": "Professional",
        "target_word_count": 1200,
        "image_suggestions": [
            {
                "description": "Hero image",
                "alt_text_template": "focus keyphrase",
                "section": "intro",
            }
        ],
        "link_suggestions": [
            {
                "anchor_text": "Related guide",
                "link_type": "internal",
                "context": "Next step",
                "section": "h2-1",
            },
            {
                "anchor_text": "Official docs",
                "link_type": "outbound",
                "context": "Source",
                "section": "h2-2",
            },
        ],
    }


def test_get_outline_schema_enforces_content_type_literal():
    from src.flow.model.structure.outline_schemas import get_outline_schema

    BlogSchema = get_outline_schema("blog")

    payload = {
        **_base_common("blog"),
        "intro": {"hook": "Hook", "context": "Context", "promise": "Promise"},
        "sections": [
            {
                "heading": "What focus keyphrase means",
                "purpose": "Define it",
                "key_points": ["Point 1", "Point 2"],
                "snippet_opportunity": True,
                "suggested_word_count": 250,
            },
            {
                "heading": "How it works in practice",
                "purpose": "Explain",
                "key_points": ["Point 1", "Point 2"],
                "suggested_word_count": 250,
            },
            {
                "heading": "Common mistakes to avoid",
                "purpose": "Prevent errors",
                "key_points": ["Point 1", "Point 2"],
                "suggested_word_count": 250,
            },
            {
                "heading": "Best practices and examples",
                "purpose": "Make it actionable",
                "key_points": ["Point 1", "Point 2"],
                "suggested_word_count": 250,
            },
        ],
        "conclusion": {"recap_points": ["Recap 1", "Recap 2"], "cta": "Try it today"},
        "schema_type": "Article",
        "table_of_contents": False,
    }

    BlogSchema.model_validate(payload)

    with pytest.raises(Exception):
        BlogSchema.model_validate({**payload, "content_type": "comparison"})


def test_validate_outline_quality_rejects_generic_headings():
    from src.flow.model.structure.outline_schemas import (
        get_outline_schema,
        validate_outline_quality,
    )

    BlogSchema = get_outline_schema("blog")
    bad = {
        **_base_common("blog"),
        "intro": {"hook": "Hook", "context": "Context", "promise": "Promise"},
        "sections": [
            {
                "heading": "Introduction",
                "purpose": "Define it",
                "key_points": ["Point 1", "Point 2"],
                "snippet_opportunity": True,
                "suggested_word_count": 250,
            },
            {
                "heading": "How it works in practice",
                "purpose": "Explain",
                "key_points": ["Point 1", "Point 2"],
                "suggested_word_count": 250,
            },
            {
                "heading": "Common mistakes to avoid",
                "purpose": "Prevent errors",
                "key_points": ["Point 1", "Point 2"],
                "suggested_word_count": 250,
            },
            {
                "heading": "Best practices and examples",
                "purpose": "Make it actionable",
                "key_points": ["Point 1", "Point 2"],
                "suggested_word_count": 250,
            },
        ],
        "conclusion": {"recap_points": ["Recap 1", "Recap 2"], "cta": "Try it today"},
        "schema_type": "Article",
        "table_of_contents": False,
    }

    model = BlogSchema.model_validate(bad)
    with pytest.raises(ValueError):
        validate_outline_quality("blog", model)


def test_validate_outline_quality_requires_sequential_steps():
    from src.flow.model.structure.outline_schemas import (
        get_outline_schema,
        validate_outline_quality,
    )

    HowToSchema = get_outline_schema("how-to-guide")
    payload = {
        **_base_common("how-to-guide"),
        "prerequisites": ["A laptop"],
        "tools_or_materials": ["Tool A"],
        "steps": [
            {
                "step_number": 1,
                "title": "Do the first thing",
                "goal": "Start",
                "instructions": ["A", "B"],
            },
            {
                "step_number": 3,
                "title": "Do the next thing",
                "goal": "Continue",
                "instructions": ["A", "B"],
            },
            {
                "step_number": 4,
                "title": "Finish up",
                "goal": "Done",
                "instructions": ["A", "B"],
            },
            {
                "step_number": 5,
                "title": "Verify results",
                "goal": "Check",
                "instructions": ["A", "B"],
            },
            {
                "step_number": 6,
                "title": "Optional hardening",
                "goal": "Improve",
                "instructions": ["A", "B"],
            },
        ],
        "wrap_up": ["You did X", "Next: Y"],
        "schema_type": "HowTo",
    }
    model = HowToSchema.model_validate(payload)
    with pytest.raises(ValueError):
        validate_outline_quality("how-to-guide", model)
