"""The reviewer's edits to the outline's sections: their order, their headings, removals.

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
"""

from __future__ import annotations

import logging
from typing import Any

from src.flow.engines.content.generation.outline_structure import (
    item_heading_field,
    resolve_outline_structure,
    section_containers,
)

logger = logging.getLogger(__name__)

HEADING_LEVELS = ("H2", "H3")


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
    if field and isinstance(heading, str) and heading.strip():
        item[field] = heading.strip()
    level = row.get("heading_level")
    if level in HEADING_LEVELS and item.get("heading_level") in HEADING_LEVELS:
        item["heading_level"] = level
    return item


def _rows_by_list(rows: list) -> dict[str, list[tuple[int, dict]]]:
    by_list: dict[str, list[tuple[int, dict]]] = {}
    seen: set[str] = set()
    for row in rows:
        row_id = row.get("id") if isinstance(row, dict) else None
        path, _, index = row_id.rpartition(":") if isinstance(row_id, str) else ("", "", "")
        if not path or not index.isdigit() or row_id in seen:
            logger.warning("[OutlineEdits] ignoring section row %r", row)
            continue
        seen.add(row_id)
        by_list.setdefault(path, []).append((int(index), row))
    return by_list


def apply_section_edits(outline: dict, content_type: str, rows: Any) -> dict:
    """The outline with the reviewer's order, headings and removals applied."""
    if not isinstance(rows, list) or not rows:
        return outline
    editable = {
        path for path, _ in section_containers(resolve_outline_structure(outline, content_type))
    }
    updated = outline
    for path, listed in _rows_by_list(rows).items():
        items = _items_at(outline, path)
        if path not in editable or items is None:
            logger.warning("[OutlineEdits] no section list at %r; rows ignored", path)
            continue
        stale = [index for index, _ in listed if index >= len(items)]
        if stale:
            logger.warning("[OutlineEdits] %s has no sections at %s; ignored", path, stale)
        reordered = [_edited_item(items[index], row) for index, row in listed if index < len(items)]
        if not reordered:
            logger.warning("[OutlineEdits] edits would empty %r; kept as it was", path)
            continue
        # A list that now opens on a subsection has no H2 above it.
        if reordered[0].get("heading_level") == "H3":
            reordered[0]["heading_level"] = "H2"
        logger.info(
            "[OutlineEdits] %s: %d of %d sections, order %s",
            path,
            len(reordered),
            len(items),
            [index for index, _ in listed],
        )
        updated = _with_items(updated, path, reordered)
    return updated
