"""A section that a typed field writes is in the article (G98, rext-control #812).

A how-to guide's steps, an in-depth review's verdict and a tutorial's prerequisites are typed
fields of their content models, so the outline's block of the same name never became a section
of the body, and nothing else put them there: a how-to guide was sections of advice without its
steps. They are rendered at assembly, where the block stands in the approved order.
"""

import copy
import json

import pytest

from src.flow.engines.content.generation.section_stream import article_section_stream
from src.flow.engines.content.generation.structured_body import (
    STRUCTURED_BLOCKS_KEY,
    _typed_heading,
    assemble_structured_payload,
    build_structured_content_model,
    sections_in_article_order,
    typed_section_blocks,
    typed_section_drafts,
)
from src.flow.engines.content.generation.subheading_seo import (
    _is_bolted_on,
    extract_subheadings,
    heading_length_issue,
    subheading_report,
)
from src.flow.engines.content.generation.validation import check_word_count_band
from src.flow.engines.content.generation.word_count_utils import (
    TYPED_SECTION_WORDS_KEY,
    compute_word_target_band,
    typed_section_allowance,
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
        "## How to Repot a Houseplant in 3 Steps\n\n"
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
    assert " Steps" not in payload["body_markdown"]
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


@pytest.mark.parametrize(
    ("written", "shown"),
    [
        ("Step 2: Mix the soil", "Mix the soil."),
        ("step 10 - Rest the plant", "Rest the plant."),
        ("Step 3 Water it", "Water it."),
        ("2) Fill the pot", "Fill the pot."),
        ("**4. Press the soil down**", "Press the soil down."),
        # A number the title starts with is no numbering.
        ("10-minute soak", "10-minute soak."),
        ("24-hour rest", "24-hour rest."),
        ("3 ways to loosen the roots", "3 ways to loosen the roots."),
        ("1.5 litres of water", "1.5 litres of water."),
        # An asterisk inside the title is the writer's, and is shown as one.
        ("Run SELECT * to inspect the table", "Run SELECT \\* to inspect the table."),
        ("Match *.log files", "Match \\*.log files."),
        # So is an underscore at a word's edge; one inside a word needs nothing.
        ("__init__", "\\_\\_init\\_\\_."),
        ("_config_", "\\_config\\_."),
        ("Set max_depth to 3", "Set max_depth to 3."),
    ],
)
def test_a_steps_title_loses_its_own_numbering_and_nothing_else(written, shown):
    steps = [{"title": written, "description": "Then go on."}]

    body = _assemble(HOW_TO_OUTLINE, "how-to-guide", _how_to_content(steps))["body_markdown"]

    assert f"\n1. **{shown}** Then go on.\n" in body


def test_a_steps_text_of_several_blocks_keeps_them_under_its_number():
    fence = "`" * 3
    steps = [
        {
            "title": "Install the tools",
            "description": f"Run this:\n\n{fence}bash\nuv sync\n{fence}",
        },
        {"title": "Check the pot", "description": "Look for:\n- drainage holes\n- cracks"},
        {"title": "Water it", "description": "Water once,\nthen let it drain."},
    ]

    body = _assemble(HOW_TO_OUTLINE, "how-to-guide", _how_to_content(steps))["body_markdown"]

    assert (
        "1. **Install the tools.** Run this:\n"
        "\n"
        f"   {fence}bash\n"
        "   uv sync\n"
        f"   {fence}\n"
        "2. **Check the pot.** Look for:\n"
        "   - drainage holes\n"
        "   - cracks\n"
        "3. **Water it.** Water once, then let it drain." in body
    )
    # The nested list's items are no steps of their own.
    assert "## How to Repot a Houseplant in 3 Steps\n" in body


@pytest.mark.parametrize(
    ("content_type", "outline", "content", "keyphrase", "heading"),
    [
        (
            "how-to-guide",
            "how-to",
            "how-to",
            KEYPHRASE,
            "How to Repot a Houseplant in 3 Steps",
        ),
        (
            "how-to-guide",
            "how-to",
            "how-to",
            "repotting houseplants",
            "Repotting Houseplants in 3 Steps",
        ),
        # A keyphrase that is a question of its own is no part of another sentence.
        (
            "how-to-guide",
            "how-to",
            "how-to",
            "what is repotting",
            "Follow These Steps in Order",
        ),
        ("how-to-guide", "how-to", "how-to", "", "Follow These Steps in Order"),
        ("in-depth-review", "review", "review", "notion review", "The Verdict on Notion Review"),
        ("in-depth-review", "review", "review", "is notion worth it", "The Verdict in a Few Words"),
        (
            "tutorial",
            "tutorial",
            "tutorial",
            "python web scraping",
            "What You Need for Python Web Scraping",
        ),
        (
            "tutorial",
            "tutorial",
            "tutorial",
            "how to build a web scraper",
            "What You Need to Build a Web Scraper",
        ),
        (
            "tutorial",
            "tutorial",
            "tutorial",
            "why scrape the web",
            "What You Need Before You Start",
        ),
    ],
)
def test_the_heading_says_the_keyphrase_as_a_part_of_it_never_before_a_colon(
    content_type, outline, content, keyphrase, heading
):
    outline = {"how-to": HOW_TO_OUTLINE, "review": REVIEW_OUTLINE, "tutorial": TUTORIAL_OUTLINE}[
        outline
    ]
    content = {
        "how-to": _how_to_content(),
        "review": {
            "title": "Notion Review for Small Teams",
            "hero": _block(None, "Notion does a lot."),
            "pros_cons": _block("Where Notion Helps and Where It Hurts", "It is flexible."),
            "verdict": "Notion suits small teams.",
        },
        "tutorial": {
            "title": "Python Web Scraping Tutorial for Beginners",
            "hero": _block(None, "Scrape a page in an afternoon."),
            "modules": _block("Set Up the Scraping Project", "Create a folder."),
            "prerequisites": ["Python 3.11"],
        },
    }[content]

    body = _assemble(outline, content_type, content, keyphrase=keyphrase)["body_markdown"]

    assert f"## {heading}\n\n" in body
    assert not _is_bolted_on(heading, keyphrase)
    assert heading_length_issue(2, heading, content_type) is None


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
        "## The Verdict on Notion Review\n\n"
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
        "## What You Need for Python Web Scraping\n\n- Python 3.11\n- A terminal\n\n"
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
    assert "in 3 Steps" not in body


@pytest.mark.parametrize(
    ("title", "has_a_heading"),
    [
        # No word proves these English, and none says otherwise: they keep their heading.
        ("Install Docker on Ubuntu", True),
        ("Python Web Scraping Tutorial", True),
        # A name from another language in a title that says it is English.
        ("How to Use La Roche-Posay Cleanser", True),
        ("What Is La Liga and How Do You Follow It", True),
        ("Wie man eine Zimmerpflanze umtopft", False),
        ("観葉植物の植え替え方法", False),
        ("Как пересадить комнатное растение", False),
    ],
)
def test_only_a_title_surely_in_another_language_loses_the_heading(title, has_a_heading):
    content = {
        "title": title,
        "hero": _block(None, "Scrape a page in an afternoon."),
        "skill_context": _block("Who This Scraping Tutorial Is For", "Beginners."),
        "modules": _block("Set Up the Scraping Project", "Create a folder."),
        "prerequisites": ["Python 3.11"],
    }

    body = _assemble(TUTORIAL_OUTLINE, "tutorial", content, keyphrase="")["body_markdown"]

    assert "- Python 3.11" in body
    assert ("## What You Need Before You Start\n\n- Python 3.11" in body) is has_a_heading


def test_a_title_that_is_not_english_gets_the_list_without_an_english_heading():
    content = _how_to_content()
    content["title"] = "Cómo trasplantar una planta de interior paso a paso"

    body = _assemble(HOW_TO_OUTLINE, "how-to-guide", content, keyphrase="cómo trasplantar")[
        "body_markdown"
    ]

    assert "Look at the roots first.\n\n1. **Remove the plant.** Ease it out of its pot.\n" in body
    assert "in 3 Steps" not in body and "Follow These Steps" not in body


# ── The length check: the section's words come on top of the maximum ──────────────────────

TARGET = 300
SPEC = {"target_word_count": TARGET}


def _words(payload):
    return len(f"{payload.get('introduction') or ''}\n\n{payload['body_markdown']}".split())


def _how_to_at_its_maximum():
    """A how-to guide whose article, as main assembles it, has exactly the band's last word."""
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    content = _how_to_content()
    content["introduction"] = "Repotting is a short job when the roots are ready for it."
    as_main = assemble_structured_payload(copy.deepcopy(content), built[1])
    room = compute_word_target_band(TARGET)[1] - _words(as_main)
    content["tools"]["markdown"] += " " + " ".join(["soil"] * room)
    return content, assemble_structured_payload(copy.deepcopy(content), built[1])


def test_a_how_to_guide_at_its_maximum_on_main_still_passes_with_its_steps():
    content, as_main = _how_to_at_its_maximum()
    _, maximum = compute_word_target_band(TARGET)
    assert _words(as_main) == maximum
    assert check_word_count_band(as_main, SPEC)["passed"]

    payload = _assemble(HOW_TO_OUTLINE, "how-to-guide", content)

    added = _words(payload) - maximum
    assert added > 0
    assert payload[TYPED_SECTION_WORDS_KEY] == added == typed_section_allowance(payload)
    result = check_word_count_band(payload, SPEC)
    assert result["passed"], result["detail"]
    assert f"-{maximum + added}." in result["detail"]


def test_the_room_stays_after_a_rewrite_reworded_the_steps_and_never_grows():
    content, _ = _how_to_at_its_maximum()
    payload = _assemble(HOW_TO_OUTLINE, "how-to-guide", content)
    was = "1. **Remove the plant.** Ease it out of its pot."
    assert was in payload["body_markdown"]

    # The rewrite hands back the body whole, the list in other words; the record is as it was.
    reworded = {
        **payload,
        "body_markdown": payload["body_markdown"].replace(
            was, "1. **Lift the plant.** Slide it from the old pot."
        ),
    }
    assert _words(reworded) == _words(payload)
    assert check_word_count_band(reworded, SPEC)["passed"]

    padded = {
        **payload,
        "body_markdown": payload["body_markdown"].replace(was, was + " Slowly."),
    }
    assert not check_word_count_band(padded, SPEC)["passed"]


@pytest.mark.parametrize("recorded", [..., None, 0, -5, True, "40", 12.5])
def test_without_a_recorded_count_there_is_no_room(recorded):
    content, _ = _how_to_at_its_maximum()
    payload = _assemble(HOW_TO_OUTLINE, "how-to-guide", content)
    if recorded is ...:
        del payload[TYPED_SECTION_WORDS_KEY]
    else:
        payload[TYPED_SECTION_WORDS_KEY] = recorded

    assert typed_section_allowance(payload) == 0
    result = check_word_count_band(payload, SPEC)
    assert not result["passed"]
    assert result["severity"] == "blocking"


def test_a_blogs_band_is_unchanged():
    payload = _assemble(BLOG_OUTLINE, "blog", BLOG_CONTENT, keyphrase="content marketing roi")
    assert TYPED_SECTION_WORDS_KEY not in payload
    assert typed_section_allowance(payload) == 0

    low, high = compute_word_target_band(TARGET)
    filler = " ".join(["word"] * (high - _words(payload)))
    at_the_maximum = {**payload, "body_markdown": f"{payload['body_markdown']} {filler}"}
    assert _words(at_the_maximum) == high
    assert check_word_count_band(at_the_maximum, SPEC)["passed"]
    one_more = {**at_the_maximum, "body_markdown": at_the_maximum["body_markdown"] + " word"}
    assert not check_word_count_band(one_more, SPEC)["passed"]


def test_assembling_a_second_time_keeps_the_recorded_count():
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    typed = typed_section_blocks(HOW_TO_OUTLINE, "how-to-guide")
    once = _assemble(HOW_TO_OUTLINE, "how-to-guide", _how_to_content())

    twice = assemble_structured_payload(
        copy.deepcopy(once), built[1], typed=typed, keyphrase=KEYPHRASE, content_type="how-to-guide"
    )

    assert twice[TYPED_SECTION_WORDS_KEY] == once[TYPED_SECTION_WORDS_KEY] > 0


# ── The heading never turns a passing subheading check into a failing one ─────────────────


def _body_with(matching, others):
    carrying = [f"## How to Repot a Houseplant: Part {n} of Many" for n in range(matching)]
    plain = [f"## Tools and Materials, Shelf Number {n}" for n in range(others)]
    return "\n\n".join(f"{heading}\n\nSome text." for heading in carrying + plain)


@pytest.mark.parametrize("total", range(1, 31))
def test_a_passing_share_of_keyphrase_headings_still_passes_with_the_sections_heading(total):
    for matching in range(total + 1):
        body = _body_with(matching, total - matching)
        before = subheading_report(body, KEYPHRASE, "how-to-guide")["keyphrase"]
        assert (before["total"], before["matching"]) == (total, matching)
        if before["status"] != "ok":
            continue

        heading = _typed_heading(
            "How to Repot a Houseplant in 3 Steps",
            "Follow These Steps in Order",
            KEYPHRASE,
            "How to Repot a Houseplant: A Step-by-Step Guide",
            body,
            "how-to-guide",
        )

        after = subheading_report(f"{body}\n\n## {heading}\n", KEYPHRASE, "how-to-guide")
        assert after["keyphrase"]["status"] == "ok", (total, matching, heading)
        assert after["length_violations"] == []


# -- While the article is still being written (rext-control #773) ----------------------------


def test_the_writing_screens_sections_are_the_articles_in_the_articles_order():
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    typed = typed_section_blocks(HOW_TO_OUTLINE, "how-to-guide")

    keys = [block.key for block in sections_in_article_order(built[1], typed)]

    # As the assembled body has them (the first test of this file).
    assert keys == ["hero", "prerequisites", "steps", "tools", "error_prevention"]
    assert [block.key for block in sections_in_article_order(built[1], [])] == [
        "hero",
        "prerequisites",
        "tools",
        "error_prevention",
    ]


def test_a_typed_section_reads_as_its_draft_with_the_plain_heading():
    steps = _how_to_content()["steps"]

    drafts = typed_section_drafts("how-to-guide", title="How to Repot a Houseplant")

    assert set(drafts) == {"steps"}
    assert drafts["steps"](steps) == (
        "Follow These Steps in Order",
        "1. **Remove the plant.** Ease it out of its pot.\n"
        "2. **Prepare the new pot.** Add fresh mix.\n"
        "3. **Water the plant!** Water it once.",
    )
    assert drafts["steps"]([]) is None and drafts["steps"](None) is None
    assert typed_section_drafts("blog") == {}
    assert set(typed_section_drafts("tutorial")) == {"prerequisites"}
    assert set(typed_section_drafts("in-depth-review")) == {"verdict"}


def test_a_draft_under_a_title_in_another_language_has_no_english_heading():
    """As in the finished article: the section then follows the one before it."""
    steps = _how_to_content()["steps"]

    drafts = typed_section_drafts("how-to-guide", title="Wie man eine Zimmerpflanze umtopft")

    heading, markdown = drafts["steps"](steps)
    assert heading == ""
    assert markdown.startswith("1. **Remove the plant.**")


def test_a_how_to_guides_steps_reach_the_writing_screen_in_their_place():
    """The whole path of one answer: the reader is set up from the approved outline, and the
    steps, which the answer holds a field each (rext-control #817), are sent as section 3 of 5
    once the last of them is written, with the list the finished article will show: the
    approved titles over the writer's instructions."""
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    content = _how_to_content(steps=[])
    written = {
        "step_1": "Ease it out of its pot.",
        "step_2": "Add fresh mix.",
        "step_3": "Water it once.",
    }
    answer = json.dumps(
        {
            "title": content["title"],
            "steps": [],
            "hero": content["hero"],
            "prerequisites": content["prerequisites"],
            **written,
            "tools": content["tools"],
            "error_prevention": content["error_prevention"],
        }
    )

    stream = article_section_stream(built[1], HOW_TO_OUTLINE, "how-to-guide", content["title"])
    sections = [
        section
        for start in range(0, len(answer), 17)
        for section in stream.feed(answer[start : start + 17])
    ]

    assert [(s["key"], s["index"], s["of"]) for s in sections] == [
        ("hero", 1, 5),
        ("prerequisites", 2, 5),
        ("steps", 3, 5),
        ("tools", 4, 5),
        ("error_prevention", 5, 5),
    ]
    assert sections[2]["heading"] == "Follow These Steps in Order"
    assert sections[2]["markdown"] == (
        "1. **Remove the plant.** Ease it out of its pot.\n"
        "2. **Prepare the new pot.** Add fresh mix.\n"
        "3. **Water the plant.** Water it once."
    )


def test_the_steps_are_sent_only_when_every_step_field_has_closed():
    """An answer's fields may come in any order: the last step written first sends nothing,
    and the section is sent whole when the step still missing closes."""
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    content = _how_to_content(steps=[])
    stream = article_section_stream(built[1], HOW_TO_OUTLINE, "how-to-guide", content["title"])

    early = json.dumps(
        {"step_3": "Water it once.", "step_1": "Ease it out.", "hero": content["hero"]}
    )
    sent = stream.feed(early[:-1])
    assert [section["key"] for section in sent] == ["hero"]

    sent = stream.feed(
        ', "step_2": "Add fresh mix.", "tools": ' + json.dumps(content["tools"]) + "}"
    )
    assert [section["key"] for section in sent] == ["steps", "tools"]
    assert sent[0]["markdown"] == (
        "1. **Remove the plant.** Ease it out.\n"
        "2. **Prepare the new pot.** Add fresh mix.\n"
        "3. **Water the plant.** Water it once."
    )


def test_the_draft_of_a_step_written_empty_is_what_the_article_will_show():
    """Assembly lets the outline's description stand in for a step written empty; the draft
    the page shows says the same, in the same place."""
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    stream = article_section_stream(built[1], HOW_TO_OUTLINE, "how-to-guide", "How to Repot")

    sent = stream.feed(json.dumps({"step_1": "Ease it out.", "step_2": "", "step_3": "Water."}))

    assert sent[0]["markdown"] == (
        "1. **Remove the plant.** Ease it out.\n"
        "2. **Prepare the new pot.** Add fresh mix.\n"
        "3. **Water the plant.** Water."
    )


def test_a_step_field_closed_as_null_is_closed_and_the_section_is_still_sent():
    """A provider answering best-effort JSON can return null for a required text: the article
    lets the plan stand in, and the page is sent the same list rather than nothing."""
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    stream = article_section_stream(built[1], HOW_TO_OUTLINE, "how-to-guide", "How to Repot")
    answer = '{"step_1": "Ease it out.", "step_2": null, "step_3": null}'

    sent = [
        section
        for piece in (answer[:30], answer[30:41], answer[41:])
        for section in stream.feed(piece)
    ]

    assert [section["key"] for section in sent] == ["steps"]
    assert sent[0]["markdown"] == (
        "1. **Remove the plant.** Ease it out.\n"
        "2. **Prepare the new pot.** Add fresh mix.\n"
        "3. **Water the plant.** Water it once."
    )


def test_a_closed_step_field_is_read_once_however_long_the_answer_grows(monkeypatch):
    built = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    stream = article_section_stream(built[1], HOW_TO_OUTLINE, "how-to-guide", "How to Repot")
    reads = []
    loads = json.loads
    monkeypatch.setattr(json, "loads", lambda text: reads.append(text) or loads(text))

    stream.feed('{"step_1": "Ease it out.", "step_2": "Add ')
    for _ in range(50):
        stream.feed("more ")
    sent = stream.feed('mix.", "step_3": "Water it once."}')

    assert [section["key"] for section in sent] == ["steps"]
    assert reads.count('"Ease it out."') == 1
    # A new answer starts from nothing.
    stream.restart()
    assert stream.feed('{"step_1": "Other."') == []


def test_the_writers_fields_stand_where_the_steps_do_in_the_approved_order():
    """The article is written in the order it is read: the step fields come after the section
    before the steps and before the one after."""
    model, _ = build_structured_content_model(
        HOW_TO_OUTLINE, "how-to-guide", get_generated_content_model("how-to-guide")
    )

    asked = [f for f in model.model_fields if f in ("prerequisites", "tools") or "step_" in f]
    assert asked == ["prerequisites", "step_1", "step_2", "step_3", "tools"]


def test_an_answer_without_section_fields_has_no_reader():
    assert article_section_stream(None, HOW_TO_OUTLINE, "how-to-guide") is None
    assert article_section_stream([], HOW_TO_OUTLINE, "how-to-guide") is None
