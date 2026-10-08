"""The article's parts, as the outline's review gate lists them for the reviewer.

The gate sends `editable_sections`: the rows of the lists a reviewer may reorder,
rename or remove (outline_edits.py). Those lists are only some of what the
article is written under. A product roundup's picks sit two levels down
(`best_picks.groups[].products[]`), so they are one block for the writer and no
rows for the gate, and the review step showed the roundup's alternatives alone
(revnix/rext-control#814): the customer approved a list the article treats as
an aside, and never saw the products it reviews.

`gate_structure` lists every part the article's body is built from, in the
approved order, from the same source the writer reads
(`resolve_outline_structure`): a part the gate offers rows for names its `list`,
any other part carries `items` to read. It is display only. Nothing here changes
the outline, the rows, or what an approval may send back.

What a part's items say is what the section will cover, never the outline's own
unverified facts: prices, ratings, scores, adoption numbers and links are left
out, because the writer may state only sourced facts and the article can differ.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.flow.engines.content.generation.outline_structure import (
    OutlineBlock,
    item_heading_field,
    resolve_expected_headings,
    resolve_outline_structure,
    section_containers,
)
from src.flow.engines.content.generation.structured_body import typed_section_blocks
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.model.structure.outlines.render import block_items

logger = logging.getLogger(__name__)

# The gate's payload is stored with the run: a part shows what it covers, not all of it.
MAX_ITEMS = 40
MAX_POINTS = 3
MAX_POINT_LENGTH = 160
MAX_LABEL_LENGTH = 120

# A field that holds a fact the outline's model wrote without a source (a price, a rating, a
# date, a comparison table's cells), or a link.
_FACT_FIELD = re.compile(
    r"price|pricing|cost|fee|rating|score|metric|percent|statistic|link|url|discount"
    r"|values$|last_updated|(?:^|_)date(?:$|_)",
    re.IGNORECASE,
)


def _typed_fields(content_type: str) -> set[str]:
    """The block keys a typed field of the content model owns (`cta`, `images`, …).

    The writer's model leaves those blocks to their typed fields
    (`build_structured_content_model`'s collision filter reads the same set from
    the same model), so they are not sections of the body. The test beside this
    module holds the two together.
    """
    model = get_generated_content_model(content_type)
    return set(model.model_fields) if model is not None else set()


def _without_facts(value: Any) -> Any:
    """The value without its fact fields, at any depth."""
    if isinstance(value, dict):
        return {
            key: _without_facts(sub) for key, sub in value.items() if not _FACT_FIELD.search(key)
        }
    if isinstance(value, list):
        return [_without_facts(item) for item in value]
    return value


def _short(text: Any, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"


def _groups(data: Any) -> list[dict] | None:
    """A block's list of dicts: the block itself, or the one list a wrapper holds."""
    if isinstance(data, dict) and len(data) == 1:
        data = next(iter(data.values()))
    if isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
        return data
    return None


def _wrapped_model(entry: dict) -> dict | None:
    """The one named model an entry wraps (a ranked product's `product`, a ranked tool's
    `tool`), when the entry has no name of its own."""
    if item_heading_field(entry):
        return None
    models = [value for value in entry.values() if isinstance(value, dict)]
    named = [model for model in models if item_heading_field(model)]
    return named[0] if len(models) == 1 and named else None


def _ranked_entries(data: Any) -> list[dict] | None:
    """A block of groups of ranked entries, as one item per entry.

    A roundup's `best_picks` is groups ("Best Overall") of ranked products; best
    tools' `rankings` is categories of ranked tools. The entry is what the
    article reviews, so it is the item: its name, then its group and why it is
    there. None for any other shape.
    """
    groups = _groups(data)
    if not groups:
        return None
    items: list[dict] = []
    for group in groups:
        lists = [
            value
            for value in group.values()
            if isinstance(value, list) and value and all(isinstance(i, dict) for i in value)
        ]
        if len(lists) != 1:
            return None
        group_name = next(
            (value for value in group.values() if isinstance(value, str) and value.strip()), ""
        )
        for entry in lists[0]:
            model = _wrapped_model(entry)
            if model is None:
                return None
            reasons = [
                value for value in entry.values() if isinstance(value, str) and value.strip()
            ]
            best_for = [
                value for value in model.get("best_for") or [] if isinstance(value, str) and value
            ]
            items.append(
                {
                    "label": model[item_heading_field(model)],
                    "points": [
                        group_name,
                        *reasons[:1],
                        *([f"Best for: {', '.join(best_for[:3])}"] if best_for else []),
                    ],
                }
            )
    return items or None


def _items(block: OutlineBlock) -> list[dict]:
    """What a part covers, to read: at most MAX_ITEMS items of MAX_POINTS short points."""
    data = _without_facts(block.data)
    raw = _ranked_entries(data) or block_items(data)
    items = []
    for item in raw:
        label = _short(item.get("label"), MAX_LABEL_LENGTH)
        points = [
            point
            for point in (_short(p, MAX_POINT_LENGTH) for p in item.get("points") or [])
            # A fallback point may repeat the item's own name.
            if point and point != label
        ][:MAX_POINTS]
        if label or points:
            items.append({"label": label, "points": points})
    return items[:MAX_ITEMS]


def gate_structure(outline: dict, content_type: str) -> list[dict]:
    """The article's parts in the approved order, for the review gate to list whole.

    One entry per block the article's body is built from: `{"key", "heading"}`
    with `"list"` (the path of a list the gate offers rows for, as in
    `editable_sections`) or `"items"` (`{"label", "points"}` each, to read).
    `heading` is the block's own name in the outline; the writer words the
    article's heading.

    Left out: the blocks that are no section of the body (the hero, the FAQ and
    the call to action, as the validator's expected headings leave them out),
    and a block a typed field of the content model owns, unless that field's
    value is written as a section (a how-to's steps, a review's verdict, a
    tutorial's prerequisites: `typed_section_blocks`).
    """
    blocks = resolve_outline_structure(outline, content_type)
    lists = {path.split(".", 1)[0]: path for path, _ in section_containers(blocks)}
    owned = _typed_fields(content_type) - {
        block.key for block in typed_section_blocks(outline, content_type)
    }
    parts: list[dict] = []
    for block in blocks:
        # Not a heading of the article: what the validator doesn't expect one for.
        if not resolve_expected_headings([block]):
            continue
        part: dict = {"key": block.key, "heading": block.heading}
        if block.key in lists:
            # The gate offers its rows, whoever writes it: the list keeps its place.
            part["list"] = lists[block.key]
        elif block.key in owned:
            continue
        else:
            items = _items(block)
            if not items:
                continue
            part["items"] = items
        parts.append(part)
    return parts


def safe_gate_structure(outline: dict, content_type: str) -> list[dict]:
    """`gate_structure`, or nothing: the list is for reading, and never fails the gate."""
    try:
        return gate_structure(outline, content_type)
    except Exception:
        logger.exception("gate_structure: content_type=%s; the gate goes without it", content_type)
        return []
