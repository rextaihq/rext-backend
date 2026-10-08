"""A how-to guide's steps are the approved ones, each written in a field of its own (G98a, #817).

The typed `steps` list left the writer to its own list: on five staging guides, four to six
steps of one sentence each whatever the outline approved (eight approved, five written, three
pairs folded). Each approved step is now a required field of the writer's model, and the list
the article shows is built from those fields at assembly: the approved titles, the approved
order, the writer's instructions under each.
"""

from src.flow.engines.content.generation.structured_body import (
    assemble_structured_payload,
    build_structured_content_model,
    typed_section_blocks,
)
from src.flow.engines.content.generation.word_count_utils import typed_section_allowance
from src.flow.model.structure.contents import get_generated_content_model

KEYPHRASE = "how to repot a houseplant"
OUTLINE = {
    "steps": {
        "steps": [
            {
                "step_number": 1,
                "title": "Remove the Plant from Its Current Pot",
                "description": "a",
            },
            {"step_number": 2, "title": "Prepare the New Pot and Soil", "description": "b"},
            {"step_number": 3, "title": "Set the Plant and Fill In", "description": "c"},
        ]
    },
    "tools": {"tools": [{"name": "Trowel", "purpose": "Moving soil", "required": True}]},
}
WRITTEN = {
    "step_1": "Tip the pot on its side and ease the root ball out. It should come out whole.",
    "step_2": "Cover the drainage hole with a shard, then add a third of the new soil.",
    "step_3": "Set the plant so its crown sits a finger below the rim.\n\nFill in and firm gently.",
}


def _assembled(written, outline=OUTLINE, **extra):
    _, blocks = build_structured_content_model(
        outline, "how-to-guide", get_generated_content_model("how-to-guide")
    )
    payload = {b.key: {"heading": b.heading, "markdown": "Prose of the section."} for b in blocks}
    payload.update({"title": "How to Repot a Houseplant Without Losing It", **written, **extra})
    return assemble_structured_payload(
        payload,
        blocks,
        typed=typed_section_blocks(outline, "how-to-guide"),
        keyphrase=KEYPHRASE,
        content_type="how-to-guide",
    )


def test_the_article_shows_every_approved_step_under_its_approved_title_in_order():
    body = _assembled(WRITTEN)["body_markdown"]

    assert "1. **Remove the Plant from Its Current Pot.** Tip the pot on its side" in body
    assert "2. **Prepare the New Pot and Soil.** Cover the drainage hole" in body
    assert "3. **Set the Plant and Fill In.** Set the plant so its crown" in body
    assert "in 3 Steps" in body
    # A step of two paragraphs keeps both under its number.
    assert "\n\n   Fill in and firm gently." in body


def test_the_typed_list_is_built_from_the_fields_and_the_fields_leave_the_payload():
    """`steps` stays in the payload for the schema markup; nothing downstream learns that the
    writer wrote a field per step."""
    payload = _assembled(WRITTEN)

    assert [step["title"] for step in payload["steps"]] == [
        "Remove the Plant from Its Current Pot",
        "Prepare the New Pot and Soil",
        "Set the Plant and Fill In",
    ]
    assert payload["steps"][1]["description"] == WRITTEN["step_2"]
    assert not [key for key in payload if key.startswith("step_")]


def test_a_list_the_writer_wrote_beside_the_fields_is_not_the_one_shown():
    own = [{"title": "Repot it", "description": "Move the plant to a bigger pot."}]

    payload = _assembled(WRITTEN, steps=own)

    assert "Repot it" not in payload["body_markdown"]
    assert len(payload["steps"]) == 3


def test_the_title_is_the_customers_whatever_the_order_of_the_approved_list():
    """A step renamed and moved at the outline step is written as approved: the place in the
    list decides, not the number it was first given."""
    reordered = {
        **OUTLINE,
        "steps": {
            "steps": [
                {"step_number": 2, "title": "Get the new pot ready first", "description": "b"},
                {"step_number": 1, "title": "Remove the Plant from Its Current Pot"},
            ]
        },
    }

    body = _assembled({"step_1": "Add soil.", "step_2": "Ease it out."}, outline=reordered)[
        "body_markdown"
    ]

    assert "1. **Get the new pot ready first.** Add soil." in body
    assert "2. **Remove the Plant from Its Current Pot.** Ease it out." in body


def test_a_step_left_unwritten_stands_with_what_the_outline_planned_for_it():
    """A required field can still come back empty. The step is not lost and the list is not
    renumbered one short: the description the customer approved stands in."""
    payload = _assembled({**WRITTEN, "step_2": "  "})

    assert [step["title"] for step in payload["steps"]] == [
        "Remove the Plant from Its Current Pot",
        "Prepare the New Pot and Soil",
        "Set the Plant and Fill In",
    ]
    assert "2. **Prepare the New Pot and Soil.** b" in payload["body_markdown"]


def test_a_step_with_nothing_written_and_nothing_planned_is_left_out():
    bare = {
        **OUTLINE,
        "steps": {"steps": [{"title": "First"}, {"title": "Second", "description": "Planned."}]},
    }

    payload = _assembled({"step_1": "", "step_2": "Written."}, outline=bare)

    assert [step["title"] for step in payload["steps"]] == ["Second"]
    assert "1. **Second.** Written." in payload["body_markdown"]


def test_the_length_check_allows_what_assembly_sets_around_the_writers_text():
    """The writer counted its own words inside the target. The section's heading, the approved
    titles and a stand-in description are set around them by assembly: the band's maximum
    grows by exactly those, never by the writer's text."""
    payload = _assembled(WRITTEN)

    own = sum(len(text.split()) for text in WRITTEN.values())
    section = payload["body_markdown"].split("## ")[1]
    assert "in 3 Steps" in section
    assert typed_section_allowance(payload) == len(("## " + section).split()) - own
    assert 0 < typed_section_allowance(payload) < own

    stood_in = _assembled({**WRITTEN, "step_2": ""})
    assert typed_section_allowance(stood_in) == (
        typed_section_allowance(payload) + 1  # the outline's "b"
    )


def test_a_step_keeps_the_tools_its_text_names():
    """The typed list keeps a step's own tools; the writer lists the article's tools once."""
    payload = _assembled(
        {**WRITTEN, "step_2": "Cover the hole with a shard, then use the trowel to add soil."},
        tools_needed=["Trowel", "Watering can"],
    )

    assert [step["tools"] for step in payload["steps"]] == [[], ["Trowel"], []]


def test_a_step_that_opens_with_a_list_or_a_code_block_keeps_it_one():
    """Set after the title on the same line, a fence is no fence and a first bullet is text."""
    body = _assembled(
        {
            **WRITTEN,
            "step_1": "- Tip the pot on its side.\n- Ease the root ball out.",
            "step_2": "```bash\nmix --soil 3 --perlite 1\n```\nThen fill a third of the pot.",
        }
    )["body_markdown"]

    assert (
        "1. **Remove the Plant from Its Current Pot.**\n\n"
        "   - Tip the pot on its side.\n   - Ease the root ball out."
    ) in body
    assert (
        "2. **Prepare the New Pot and Soil.**\n\n"
        "   ```bash\n   mix --soil 3 --perlite 1\n   ```\n   Then fill a third of the pot."
    ) in body
    assert "in 3 Steps" in body


def test_a_payload_without_step_fields_keeps_the_list_it_has():
    """An article written before the fields existed, or one assembled once already."""
    own = [{"title": "Repot it", "description": "Move the plant to a bigger pot."}]

    payload = _assembled({}, steps=own)

    assert "1. **Repot it.** Move the plant to a bigger pot." in payload["body_markdown"]
    assert payload["steps"] == own
