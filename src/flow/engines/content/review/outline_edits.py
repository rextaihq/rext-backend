"""The reviewer's edits to the outline's sections: their order, their headings, removals, additions.

The review gate sends `editable_sections`, one row per section the article will
be written under, each with an id that names where the section lives in the
outline ("content_structure.sections:2"). Approval may send `sections` back: the
rows in the order the user wants, with edited headings. `apply_section_edits`
writes that into the outline itself, so the writer, the validator and the
structured body (which all read the live outline through
`resolve_outline_structure`) follow the user's order without knowing an edit
happened.

Rules, chosen so a partial or stale payload can never lose a section silently:
  * a row moves only within its own list; the id decides the list
  * a list that no row names is left exactly as it was
  * a section of a named list that no row names is removed (the user deleted it),
    unless that would leave the list empty, in which case the list is kept
  * an unknown or repeated id, or a blank heading, is ignored and logged

A reviewer may also add a section: a row with `"new": true`, its list and its
heading, at the place it should go. Only lists of sections with their own
heading take one (`addable_lists`, which the gate sends as `section_additions`):
a list of entries keyed by a name, a term or a question (tools, glossary terms)
needs data a heading alone can't give. An added section has its heading and the
level and word budget of its neighbours, and no invented plan: the writer
writes it from its heading, as a required planned section.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.flow.engines.content.generation.outline_structure import (
    FAQ_HEADING,
    item_heading_field,
    resolve_outline_structure,
    section_containers,
)

logger = logging.getLogger(__name__)

HEADING_LEVELS = ("H2", "H3", "H4")
# More than this many added sections in one approval is not a review any more;
# the rest are ignored and logged.
MAX_ADDED_SECTIONS = 6
# A list item's own number in its heading: "5. SEO.ai …", "2) Surfer …".
_NUMBERED_HEADING = re.compile(r"^(\d{1,2})([.)])(\s+)")


def _row_id(path: str, index: int) -> str:
    return f"{path}:{index}"


def editable_sections(outline: dict, content_type: str) -> list[dict]:
    """The rows the review UI may reorder, rename or remove, in the outline's order."""
    rows = []
    blocks = resolve_outline_structure(outline, content_type)
    for path, items in section_containers(blocks):
        for index, item in enumerate(items):
            field = item_heading_field(item)
            if not field:
                continue
            row = {"id": _row_id(path, index), "list": path, "heading": item[field].strip()}
            if item.get("heading_level") in HEADING_LEVELS:
                row["heading_level"] = item["heading_level"]
            rows.append(row)
    return rows


def addable_lists(outline: dict, content_type: str) -> list[str]:
    """The section lists a new section may be added to: every item has its own `heading`."""
    return [
        path
        for path, items in section_containers(resolve_outline_structure(outline, content_type))
        if all(item_heading_field(item) == "heading" for item in items)
    ]


def _added_item(siblings: list[dict], row: dict) -> dict | None:
    """A new section from a reviewer's row: the heading, and its neighbours' level and budget."""
    heading = row.get("heading")
    if not isinstance(heading, str) or not heading.strip():
        return None
    item: dict = {"heading": heading.strip(), "description": "", "key_points": []}
    if any(sibling.get("heading_level") in HEADING_LEVELS for sibling in siblings):
        level = row.get("heading_level")
        item["heading_level"] = level if level in HEADING_LEVELS else "H2"
    budgets = sorted(
        sibling["suggested_word_count"]
        for sibling in siblings
        if isinstance(sibling.get("suggested_word_count"), int)
    )
    if budgets:
        item["suggested_word_count"] = budgets[len(budgets) // 2]
    return item


def _items_at(outline: dict, path: str) -> list | None:
    node: Any = outline
    for key in path.split("."):
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, list) else None


def _with_items(outline: dict, path: str, items: list) -> dict:
    """A copy of the outline with the list at `path` replaced (one or two levels)."""
    head, _, rest = path.partition(".")
    if not rest:
        return {**outline, head: items}
    return {**outline, head: {**(outline.get(head) or {}), rest: items}}


def _edited_item(item: dict, row: dict) -> dict:
    item = dict(item)
    heading = row.get("heading")
    field = item_heading_field(item)
    # The FAQ section keeps a mark whatever it's renamed to, so the writer puts the
    # FAQs there rather than adding another FAQ section (G71, revnix/rext-control#587).
    if field and FAQ_HEADING.search(item[field]):
        item["holds_faqs"] = True
    if field and isinstance(heading, str) and heading.strip():
        item[field] = heading.strip()
    level = row.get("heading_level")
    if level in HEADING_LEVELS and item.get("heading_level") in HEADING_LEVELS:
        item["heading_level"] = level
    return item


def _renumbered(items: list[dict]) -> list[dict]:
    """The list's numbered headings ("1. …", "2. …") numbered again in their new order.

    A moved item kept its old number ("5. SEO.ai" third), and the writer put it back
    where its number said (G70, revnix/rext-control#586). Lists with fewer than two
    numbered headings are left alone: one number is part of its heading.
    """
    numbered = [
        index
        for index, item in enumerate(items)
        if (field := item_heading_field(item)) and _NUMBERED_HEADING.match(item[field])
    ]
    if len(numbered) < 2:
        return items
    items = list(items)
    for position, index in enumerate(numbered, 1):
        item = dict(items[index])
        field = item_heading_field(item)
        item[field] = _NUMBERED_HEADING.sub(
            lambda match, n=position: f"{n}{match.group(2)}{match.group(3)}", item[field], count=1
        )
        items[index] = item
    return items


def _rows_by_list(rows: list) -> dict[str, list[tuple[int | None, dict]]]:
    """Each list's rows in order: (index, row) for a section the gate offered, (None, row) for an added one."""
    by_list: dict[str, list[tuple[int | None, dict]]] = {}
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, dict) and row.get("new") is True:
            path = row.get("list")
            if isinstance(path, str) and path:
                by_list.setdefault(path, []).append((None, row))
            else:
                # Never the row itself: its heading is the reviewer's text.
                logger.warning("[OutlineEdits] ignoring an added section without a list")
            continue
        row_id = row.get("id") if isinstance(row, dict) else None
        path, _, index = row_id.rpartition(":") if isinstance(row_id, str) else ("", "", "")
        if not path or not index.isdigit() or row_id in seen:
            logger.warning("[OutlineEdits] ignoring a section row without a valid id, or a repeat")
            continue
        seen.add(row_id)
        by_list.setdefault(path, []).append((int(index), row))
    return by_list


def apply_section_edits(outline: dict, content_type: str, rows: Any) -> dict:
    """The outline with the reviewer's order, headings, removals and additions applied."""
    if not isinstance(rows, list) or not rows:
        return outline
    editable = {
        path for path, _ in section_containers(resolve_outline_structure(outline, content_type))
    }
    addable = set(addable_lists(outline, content_type))
    added = 0
    updated = outline
    for path, listed in _rows_by_list(rows).items():
        items = _items_at(outline, path)
        if path not in editable or items is None:
            # The path is the client's text here (a row's id or list), so it isn't logged.
            logger.warning("[OutlineEdits] rows for a section list the outline hasn't got; ignored")
            continue
        stale = [index for index, _ in listed if index is not None and index >= len(items)]
        if stale:
            logger.warning("[OutlineEdits] %s has no sections at %s; ignored", path, stale)
        # Rows that name no section the list has (only additions, or ids it no longer
        # has) only add to it: the list stays as it is, so such a payload never reads
        # as "remove the rest".
        names_sections = any(index is not None and index < len(items) for index, _ in listed)
        reordered = [] if names_sections else list(items)
        for index, row in listed:
            if index is not None:
                if index < len(items):
                    reordered.append(_edited_item(items[index], row))
                continue
            new_item = _added_item(items, row) if path in addable else None
            if new_item is None or added >= MAX_ADDED_SECTIONS:
                reason = (
                    "the list takes no additions"
                    if path not in addable
                    else "no heading"
                    if new_item is None
                    else f"past the cap of {MAX_ADDED_SECTIONS}"
                )
                logger.warning("[OutlineEdits] an added section in %r not taken: %s", path, reason)
                continue
            added += 1
            reordered.append(new_item)
        if not reordered:
            logger.warning("[OutlineEdits] edits would empty %r; kept as it was", path)
            continue
        # A list that now opens on a subsection has no H2 above it.
        if reordered[0].get("heading_level") in ("H3", "H4"):
            reordered[0]["heading_level"] = "H2"
        reordered = _renumbered(reordered)
        logger.info(
            "[OutlineEdits] %s: %d of %d sections, order %s",
            path,
            len(reordered),
            len(items),
            [index if index is not None else "new" for index, _ in listed],
        )
        updated = _with_items(updated, path, reordered)
    return updated
