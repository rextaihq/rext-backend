"""An outline's CTA fields steer the article and never appear in it as label lines (G48).

A Best Tools article on staging printed its hero's `primary_cta` / `secondary_cta` as
"**Primary CTA:** Explore Features" under its first section: the writer's prompt listed
them as fields ("- Primary CTA: Explore Features") and the model copied them. For every
content type whose outline carries CTA fields, the prompt now says what to invite and
where, and a guard drops a line that prints such a field as a label with its value.
"""

from __future__ import annotations

import re
import typing
from typing import Any, Union, get_args, get_origin

import pytest
from pydantic import BaseModel

from src.flow.engines.content.generation.cta_labels import (
    outline_cta_labels,
    strip_cta_label_lines,
    strip_cta_labels,
)
from src.flow.engines.content.generation.outline_structure import (
    format_guidance_for_prompt,
    format_structure_for_prompt,
    humanize_key,
    is_cta_key,
    resolve_guidance_blocks,
    resolve_outline_structure,
)
from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL


def _unwrap(annotation: Any) -> Any:
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _sample(annotation: Any, found: dict[str, str], depth: int = 0, in_cta: bool = False) -> Any:
    """A minimal outline value holding only the CTA text fields under `annotation`, and the
    text fields a CTA block holds beside them."""
    annotation = _unwrap(annotation)
    if depth > 6:
        return None
    if get_origin(annotation) in (list, typing.List):
        inner = get_args(annotation)
        item = _sample(inner[0], found, depth + 1, in_cta) if inner else None
        return [item] if item else None
    if not _is_model(annotation):
        return None
    data: dict[str, Any] = {}
    for name, field in annotation.model_fields.items():
        cta = in_cta or is_cta_key(name)
        if cta and _unwrap(field.annotation) is str:
            value = f"Try the {name.replace('_', ' ')} offer {len(found) + 1}"
            found[name] = value
            data[name] = value
        else:
            sub = _sample(field.annotation, found, depth + 1, cta)
            if sub:
                data[name] = sub
    return data or None


def _cta_outline(content_type: str) -> tuple[dict, dict[str, str]]:
    found: dict[str, str] = {}
    outline = _sample(CONTENT_TYPE_TO_MODEL[content_type], found) or {}
    return outline, found


def _prompt(outline: dict, content_type: str) -> str:
    return "\n".join(
        [
            format_structure_for_prompt(resolve_outline_structure(outline, content_type)),
            format_guidance_for_prompt(resolve_guidance_blocks(outline, content_type)),
        ]
    )


def _types_with_cta_in_prompt() -> list[str]:
    types = []
    for content_type in sorted(CONTENT_TYPE_TO_MODEL):
        outline, found = _cta_outline(content_type)
        prompt = _prompt(outline, content_type)
        if any(value in prompt for value in found.values()):
            types.append(content_type)
    return types


AFFECTED = _types_with_cta_in_prompt()


def test_the_best_tools_and_the_other_cta_types_are_covered():
    # The type the staging article was, and enough of the 26 schemas with CTA fields
    # that a registry change can't quietly empty this list.
    assert "best-tools" in AFFECTED
    assert len(AFFECTED) >= 15


@pytest.mark.parametrize("content_type", AFFECTED)
def test_the_writer_is_told_what_to_invite_never_given_a_cta_label(content_type):
    outline, found = _cta_outline(content_type)
    prompt = _prompt(outline, content_type)
    for key, value in found.items():
        if value not in prompt:
            continue  # a top-level scalar the structure doesn't list
        label_line = re.compile(rf"^\s*-\s*{re.escape(humanize_key(key))}\s*:", re.M | re.I)
        assert not label_line.search(prompt), f"{content_type}: '{humanize_key(key)}:' listed"
        if is_cta_key(key):
            assert f'Invite the reader to "{value}"' in prompt
        else:
            assert f'in your own words: "{value}"' in prompt


@pytest.mark.parametrize("content_type", AFFECTED)
def test_a_cta_label_line_is_dropped_from_the_article(content_type):
    outline, found = _cta_outline(content_type)
    label_lines = [f"**{humanize_key(key)}:** {value}" for key, value in found.items()]
    body = "\n".join(
        ["## Why these tools", "", "A real paragraph stays.", *label_lines, "", "End."]
    )

    cleaned = strip_cta_labels({"body_markdown": body}, outline)["body_markdown"]

    assert "A real paragraph stays." in cleaned and "End." in cleaned
    for line in label_lines:
        assert line not in cleaned


BEST_TOOLS_OUTLINE = {
    "hero": {
        "headline": "Best AI Writing Tools",
        "subheadline": "Picked for agencies",
        "primary_cta": "Explore Features",
        "secondary_cta": "Compare Tools",
    }
}


def test_the_staging_article_loses_exactly_its_two_label_lines():
    content = {
        "introduction": "Choosing a writing tool is hard.",
        "body_markdown": (
            "## How we picked\n\nWe tested each tool for a month.\n\n"
            "**Primary CTA:** Explore Features\n**Secondary CTA:** Compare Tools\n\n"
            "## The tools\n\nExplore Features of each tool below, then compare them."
        ),
    }

    cleaned = strip_cta_labels(content, BEST_TOOLS_OUTLINE)

    assert "Primary CTA" not in cleaned["body_markdown"]
    assert "Secondary CTA" not in cleaned["body_markdown"]
    # The CTA as prose stays: it is the call to action the outline asked for.
    assert "Explore Features of each tool below" in cleaned["body_markdown"]
    assert cleaned["introduction"] == content["introduction"]


@pytest.mark.parametrize(
    "line",
    [
        "Primary CTA: Explore Features",
        "- **Secondary CTA**: Compare Tools",
        "* **Primary CTA:** [Explore Features](https://example.com/tools)",
        "__Primary CTA:__ “Explore Features.”",
        "Primary Call To Action: Explore Features",
    ],
)
def test_each_label_shape_is_dropped(line):
    labels = outline_cta_labels(BEST_TOOLS_OUTLINE)
    assert strip_cta_label_lines(f"Before.\n{line}\nAfter.", labels) == "Before.\nAfter."


def test_an_article_about_calls_to_action_keeps_its_text():
    body = (
        "## What a CTA is\n\n"
        "**Primary CTA:** the one action you want a visitor to take.\n"
        "**Secondary CTA:** a softer option, like reading a case study.\n"
        "A strong CTA: short, specific and visible.\n"
        "Every page needs a primary CTA: make it obvious.\n"
        "Our advice: Explore Features before you buy."
    )
    content = {"body_markdown": body}

    assert strip_cta_labels(content, BEST_TOOLS_OUTLINE) is content


def test_a_cta_blocks_supporting_line_is_an_instruction_and_its_label_line_goes():
    outline = {
        "cta": {
            "primary_cta": "Start Free Trial",
            "reassurance_text": "No bias rankings. Based on real use cases.",
        }
    }
    prompt = format_structure_for_prompt(resolve_outline_structure(outline, "alternatives"))
    assert "Reassurance Text:" not in prompt
    assert 'its reassurance text in your own words: "No bias rankings.' in prompt

    body = (
        "Pick the tool that fits.\n**Reassurance Text:** No bias rankings. Based on real use cases."
    )
    assert strip_cta_labels({"body_markdown": body}, outline)["body_markdown"] == (
        "Pick the tool that fits."
    )


def test_an_outline_without_ctas_changes_nothing():
    content = {"body_markdown": "**Primary CTA:** Explore Features"}
    assert strip_cta_labels(content, {"sections": [{"heading": "Intro"}]}) is content
