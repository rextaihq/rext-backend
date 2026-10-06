"""An outline's call-to-action fields steer the article; their labels never appear in it.

Outlines name their calls to action in fields such as `primary_cta`, `secondary_cta`,
`final_cta` or `cta_text` (24 content types do), and a CTA block carries lines beside
them (`reassurance_text`, `urgency_message`, `context_line`, ...). The writer is told what each one
invites and where (`outline_structure` renders them as instructions, not as fields),
and as the last line of defence this module drops a line of the article that is
nothing but such a field printed as a label with the outline's own value:

    **Primary CTA:** Explore Features

Only that exact shape goes: a label this outline defines, at the start of its own
line, followed by the value the outline gave it. A sentence that mentions a CTA, or a
"Primary CTA:" line carrying any other text, stays, so an article about calls to
action keeps its words.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.flow.engines.content.generation.outline_structure import humanize_key, is_cta_key

logger = logging.getLogger(__name__)

# The article's text fields a label line can land in.
_TEXT_FIELDS = ("introduction", "body_markdown", "conclusion")

_MAX_DEPTH = 8

# "**Primary CTA:** Explore Features", "- **Secondary CTA**: Compare Tools", "Primary CTA: X".
_LABEL_LINE = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?(?:\*\*|__)?[ \t]*(?P<label>[^:*_\n]{1,60}?)[ \t]*"
    r"(?:\*\*|__)?[ \t]*:[ \t]*(?:\*\*|__)?[ \t]*(?P<value>.*?)[ \t]*$"
)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def _norm(text: str) -> str:
    text = _LINK.sub(r"\1", str(text))
    text = text.strip().strip("\"'“”‘’*_`").strip()
    return re.sub(r"\s+", " ", text.rstrip(".!")).strip().lower()


def _strings(value: Any, depth: int = 0) -> list[str]:
    if depth > _MAX_DEPTH or value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v, depth + 1)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v, depth + 1)]
    return []


def _labels_for(key: str) -> set[str]:
    label = humanize_key(key)
    return {_norm(label), _norm(re.sub(r"\bCTAs?\b", "Call To Action", label))}


def outline_cta_labels(outline: Any) -> dict[str, set[str]]:
    """Each CTA field the outline fills, and each field a CTA block holds beside them
    (`reassurance_text`, `urgency_message`, ...), as its printed label (lower case) ->
    the values it holds."""
    found: dict[str, set[str]] = {}

    def walk(node: Any, depth: int, in_cta: bool) -> None:
        if depth > _MAX_DEPTH:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                cta = in_cta or is_cta_key(key)
                if cta:
                    values = {_norm(s) for s in _strings(value)} - {""}
                    if values:
                        for label in _labels_for(key):
                            found.setdefault(label, set()).update(values)
                walk(value, depth + 1, cta)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1, in_cta)

    walk(outline or {}, 0, False)
    return found


def strip_cta_label_lines(text: str, labels: dict[str, set[str]]) -> str:
    """`text` without its lines that print an outline CTA field as a label with its value."""
    if not text or not labels:
        return text

    def is_label_line(line: str) -> bool:
        match = _LABEL_LINE.match(line)
        if not match:
            return False
        values = labels.get(_norm(match.group("label")))
        return bool(values) and _norm(match.group("value")) in values

    lines = text.split("\n")
    kept = [line for line in lines if not is_label_line(line)]
    if len(kept) == len(lines):
        return text
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip("\n")


def strip_cta_labels(content: dict, outline: Any, *, stage: str = "") -> dict:
    """The article's text fields without outline CTA label lines (the same dict when none)."""
    labels = outline_cta_labels(outline)
    if not labels or not isinstance(content, dict):
        return content
    cleaned = dict(content)
    removed = []
    for field in _TEXT_FIELDS:
        text = content.get(field)
        if isinstance(text, str) and text:
            stripped = strip_cta_label_lines(text, labels)
            if stripped != text:
                cleaned[field] = stripped
                removed.append(field)
    if not removed:
        return content
    logger.warning("strip_cta_labels: stage=%s removed CTA label lines from %s", stage, removed)
    return cleaned
