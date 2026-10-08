"""A section that a typed field writes is in the article (G98, rext-control #812).

A how-to guide's steps, an in-depth review's verdict and a tutorial's prerequisites are typed
fields of their content models, so the outline's block of the same name never became a section
of the body, and nothing else put them there: a how-to guide was sections of advice without its
steps. They are rendered at assembly, where the block stands in the approved order.
"""

import copy

import pytest

from src.flow.engines.content.generation.structured_body import (
    STRUCTURED_BLOCKS_KEY,
    assemble_structured_payload,
    build_structured_content_model,
    typed_section_blocks,
)
from src.flow.engines.content.generation.subheading_seo import (
    extract_subheadings,
    heading_length_issue,
    subheading_report,
)
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.model.structure.contents.base import ContentBlock, blocks_to_body_markdown

KEYPHRASE = "how to repot a houseplant"

HOW_TO_OUTLINE = {
    "focus_keyphrase": KEYPHRASE,
    "hero": {"headline": "Repot a houseplant without the mess"},
    "prerequisites": {"items": [{"name": "A pot one size up"}]},
    "steps": {
        "steps": [
            {"step_number": 1, "title": "Remove the plant", "description": "Ease it out."},
            {"step_number": 2, "title": "Prepare the new pot", "description": "Add fresh mix."},
            {"step_number": 3, "title": "Water the plant", "description": "Water it once."},
        ]
    },
    "tools": {"tools": [{"name": "Trowel", "purpose": "Moving soil", "required": True}]},
    "error_prevention": {
        "errors": [{"mistake": "Overwatering", "consequence": "Rot", "solution": "Wait"}]
    },
}


def _block(heading, markdown):
    return {"heading": heading, "markdown": markdown}


def _how_to_content(steps=...):
    content = {
        "title": "How to Repot a Houseplant: A Step-by-Step Guide",
        "body_markdown": "",
        "hero": _block(None, "Repotting gives crowded roots room to grow."),
        "prerequisites": _block("What to Check Before You Repot", "Look at the roots first."),
        "tools": _block("Tools and Materials for Repotting", "A trowel and fresh mix."),
        "error_prevention": _block("Repotting Mistakes Worth Avoiding", "Do not overwater."),
    }
    if steps is ...:
        steps = [
            {"title": "Remove the plant", "description": "Ease it out of its pot.", "tools": []},
            {"title": "Step 2: Prepare the new pot", "description": "Add fresh\nmix."},
            {"title": "3. Water the plant!", "description": "Water it once.", "tools": ["Can"]},
        ]
    if steps is not None:
        content["steps"] = steps
    return content


def _assemble(outline, content_type, content, keyphrase=KEYPHRASE):
    built = build_structured_content_model(
        outline, content_type, get_generated_content_model(content_type)
    )
    assert built is not None
    return assemble_structured_payload(
        copy.deepcopy(content),
        built[1],
        typed=typed_section_blocks(outline, content_type),
        keyphrase=keyphrase,
        content_type=content_type,
    )


def test_a_how_to_guides_steps_stand_where_the_outline_has_them_numbered_in_order():
    content = _how_to_content()

    payload = _assemble(HOW_TO_OUTLINE, "how-to-guide", content)

    assert payload["body_markdown"] == (
        "Repotting gives crowded roots room to grow.\n\n"
        "## What to Check Before You Repot\n\nLook at the roots first.\n\n"
        "## How to Repot a Houseplant: Step by Step\n\n"
        "1. **Remove the plant.** Ease it out of its pot.\n"
        "2. **Prepare the new pot.** Add fresh mix.\n"
        "3. **Water the plant!** Water it once.\n\n"
        "## Tools and Materials for Repotting\n\nA trowel and fresh mix.\n\n"
        "## Repotting Mistakes Worth Avoiding\n\nDo not overwater."
    )
    # The typed list stays in the payload as the writer wrote it, and the section counts as written.
    assert payload["steps"] == content["steps"]
    assert "steps" in payload[STRUCTURED_BLOCKS_KEY]


@pytest.mark.parametrize(
    "steps",
    [None, [], [{}], [{"title": "  ", "description": ""}], "not a list"],
    ids=["no field", "empty", "an empty step", "a blank step", "not a list"],
)
def test_a_how_to_guide_without_typed_steps_gets_no_section_and_no_empty_heading(steps):
    content = _how_to_content(steps)
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )

    payload = _assemble(HOW_TO_OUTLINE, "how-to-guide", content)

    assert (
        payload["body_markdown"]
        == (assemble_structured_payload(copy.deepcopy(content), built[1])["body_markdown"])
    )
    assert "Step by Step" not in payload["body_markdown"]
    assert "steps" not in payload[STRUCTURED_BLOCKS_KEY]


def test_a_step_without_a_title_or_without_a_text_is_still_a_numbered_step():
    steps = [
        {"title": "Remove the plant", "description": ""},
        {"title": "", "description": "Add fresh mix to the new pot."},
        {"description": None},
        {"title": "Water it", "description": "Once, then let it drain."},
    ]

    body = _assemble(HOW_TO_OUTLINE, "how-to-guide", _how_to_content(steps))["body_markdown"]

    assert (
        "1. **Remove the plant.**\n"
        "2. Add fresh mix to the new pot.\n"
        "3. **Water it.** Once, then let it drain." in body
    )


def test_assembling_a_second_time_adds_nothing():
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    typed = typed_section_blocks(HOW_TO_OUTLINE, "how-to-guide")
    once = _assemble(HOW_TO_OUTLINE, "how-to-guide", _how_to_content())

    # The repair and the rewrite hand back the body whole and the typed list again.
    twice = assemble_structured_payload(
        copy.deepcopy(once), built[1], typed=typed, keyphrase=KEYPHRASE, content_type="how-to-guide"
    )

    assert twice["body_markdown"] == once["body_markdown"]
    assert twice["body_markdown"].count("1. **Remove the plant.**") == 1


def test_an_error_while_rendering_leaves_the_body_as_it_was(monkeypatch):
    from src.flow.engines.content.generation import structured_body

    def broken(*args, **kwargs):
        raise RuntimeError("no heading today")

    monkeypatch.setattr(structured_body, "_typed_heading", broken)
    content = _how_to_content()
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )

    payload = _assemble(HOW_TO_OUTLINE, "how-to-guide", content)

    assert payload == assemble_structured_payload(copy.deepcopy(content), built[1])
    assert payload["steps"] == content["steps"]


def test_only_the_sections_are_rendered_never_the_call_to_action_or_the_images():
    outline = {**HOW_TO_OUTLINE, "cta": {"primary": "Shop pots"}, "images": [{"alt": "A pot"}]}

    assert [block.key for block in typed_section_blocks(outline, "how-to-guide")] == ["steps"]
    assert typed_section_blocks(outline, "blog") == []
    assert typed_section_blocks(outline, "landing-page") == []


BLOG_OUTLINE = {
    "title": "Content Marketing ROI for Small Business: A Practical Guide",
    "structure": {
        "sections": [
            {
                "heading": "Why content marketing ROI is hard to measure",
                "heading_level": "H2",
                "description": "Explain why.",
                "key_points": ["attribution gaps", "long sales cycles"],
                "suggested_word_count": 400,
            },
            {
                "heading": "The metrics small businesses should track",
                "heading_level": "H2",
                "description": "Explain which.",
                "key_points": ["leads per post", "cost per lead"],
                "suggested_word_count": 400,
            },
        ]
    },
}
BLOG_CONTENT = {
    "title": "Content Marketing ROI for Small Business: A Practical Guide",
    "introduction": "Most small businesses publish and hope.",
    "body_markdown": "The writer's own copy of the body, which assembly replaces.",
    "structure_1": _block(
        "Why content marketing ROI is hard to measure",
        "Attribution has gaps.\n\n### Long sales cycles\n\nA sale closes months later.",
    ),
    "structure_2": _block(
        "The metrics small businesses should track",
        "- Leads per post\n- Cost per lead",
    ),
    # A blog that happens to carry these names writes them nowhere.
    "steps": [{"title": "A step", "description": "That is no part of a blog."}],
    "verdict": "No verdict in a blog.",
}
BLOG_BODY = (
    "## Why content marketing ROI is hard to measure\n\n"
    "Attribution has gaps.\n\n### Long sales cycles\n\nA sale closes months later.\n\n"
    "## The metrics small businesses should track\n\n"
    "- Leads per post\n- Cost per lead"
)


def test_a_blog_assembles_as_before_byte_for_byte():
    built = build_structured_content_model(
        BLOG_OUTLINE, "blog", get_generated_content_model("blog")
    )
    assert built is not None
    blocks = built[1]
    as_before = assemble_structured_payload(copy.deepcopy(BLOG_CONTENT), blocks)

    payload = _assemble(BLOG_OUTLINE, "blog", BLOG_CONTENT, keyphrase="content marketing roi")

    assert payload["body_markdown"] == BLOG_BODY
    assert payload == as_before
    # And as the blocks alone give it, without this module's assembly at all.
    assert BLOG_BODY == blocks_to_body_markdown(
        [(block.key, ContentBlock(**BLOG_CONTENT[block.key])) for block in blocks],
        levels={block.key: block.level for block in blocks},
    )


REVIEW_OUTLINE = {
    "hero": {"headline": "Notion, reviewed"},
    "pros_cons": {"pros": ["Flexible"], "cons": ["Slow offline"]},
    "verdict": {"summary": "Worth it for small teams"},
    "faqs": {"questions": ["Is Notion free?"]},
}
TUTORIAL_OUTLINE = {
    "hero": {"headline": "Build a scraper"},
    "skill_context": {"level": "Beginner"},
    "prerequisites": {"items": ["Python 3.11", "A terminal"]},
    "modules": {"modules": [{"title": "Set up the project"}]},
}


def test_a_reviews_verdict_is_a_section_where_the_outline_has_it():
    content = {
        "title": "Notion Review: Is It Worth It for Small Teams?",
        "hero": _block(None, "Notion does a lot."),
        "pros_cons": _block("Where Notion Helps and Where It Hurts", "It is flexible."),
        "faqs": _block("Questions About Notion, Answered", "### Is Notion free?\n\nPartly."),
        "verdict": "Notion suits small teams.\n\nLarger ones outgrow its permissions.",
    }

    payload = _assemble(REVIEW_OUTLINE, "in-depth-review", content, keyphrase="notion review")

    assert payload["body_markdown"] == (
        "Notion does a lot.\n\n"
        "## Where Notion Helps and Where It Hurts\n\nIt is flexible.\n\n"
        "## Notion Review: The Verdict\n\n"
        "Notion suits small teams.\n\nLarger ones outgrow its permissions.\n\n"
        "## Questions About Notion, Answered\n\n### Is Notion free?\n\nPartly."
    )
    assert payload["verdict"] == content["verdict"]


def test_a_tutorials_prerequisites_are_a_section_where_the_outline_has_them():
    content = {
        "title": "Python Web Scraping Tutorial for Beginners",
        "hero": _block(None, "Scrape a page in an afternoon."),
        "skill_context": _block("Who This Scraping Tutorial Is For", "Beginners."),
        "modules": _block("Set Up the Scraping Project", "Create a folder."),
        "prerequisites": ["Python 3.11", "  A terminal ", ""],
    }

    payload = _assemble(TUTORIAL_OUTLINE, "tutorial", content, keyphrase="python web scraping")

    assert payload["body_markdown"] == (
        "Scrape a page in an afternoon.\n\n"
        "## Who This Scraping Tutorial Is For\n\nBeginners.\n\n"
        "## Python Web Scraping: What You Need First\n\n- Python 3.11\n- A terminal\n\n"
        "## Set Up the Scraping Project\n\nCreate a folder."
    )


@pytest.mark.parametrize(
    ("content_type", "outline", "content", "keyphrase"),
    [
        ("how-to-guide", HOW_TO_OUTLINE, _how_to_content(), KEYPHRASE),
        ("how-to-guide", HOW_TO_OUTLINE, _how_to_content(), ""),
        (
            "how-to-guide",
            HOW_TO_OUTLINE,
            _how_to_content(),
            "how to repot a large root bound houseplant without damaging its roots at home",
        ),
    ],
    ids=["a keyphrase", "no keyphrase", "a keyphrase too long for a heading"],
)
def test_the_sections_heading_is_inside_the_heading_length_rule(
    content_type, outline, content, keyphrase
):
    body = _assemble(outline, content_type, content, keyphrase=keyphrase)["body_markdown"]

    assert subheading_report(body, keyphrase, content_type)["length_violations"] == []
    headings = [heading.text for heading in extract_subheadings(body)]
    assert len(headings) == 4  # the three written sections and the steps', no heading per step
    for heading in headings:
        assert heading_length_issue(2, heading, content_type) is None


def test_the_heading_leaves_the_keyphrase_out_when_too_many_headings_carry_it():
    content = _how_to_content()
    content["prerequisites"] = _block("How to Repot a Houseplant: What to Check", "The roots.")
    content["tools"] = _block("Tools to Repot a Houseplant at Home", "A trowel.")
    content["error_prevention"] = _block("How to Repot a Houseplant Without Rot", "Wait.")

    body = _assemble(HOW_TO_OUTLINE, "how-to-guide", content)["body_markdown"]

    assert "## Follow These Steps in Order\n\n1. **Remove the plant.**" in body
    assert "Step by Step" not in body


def test_a_title_that_is_not_english_gets_the_list_without_an_english_heading():
    content = _how_to_content()
    content["title"] = "Cómo trasplantar una planta de interior paso a paso"

    body = _assemble(HOW_TO_OUTLINE, "how-to-guide", content, keyphrase="cómo trasplantar")[
        "body_markdown"
    ]

    assert "Look at the roots first.\n\n1. **Remove the plant.** Ease it out of its pot.\n" in body
    assert "Step by Step" not in body and "Follow These Steps" not in body
