"""The article's sections, read out of the writer's answer while it is still being written.

The writer answers once, with one field per section, and the answer arrives in pieces. The
page was looking in those pieces for `body_markdown`, which is only put together after the
answer ends, so no text showed for the whole wait (rext-control#773). A measured run: the
sections arrive from 27 to 45 seconds after approval, one every 2 to 3 seconds, and the
finished article at 171.

`SectionStream` is fed the pieces as they come and returns each section the moment its part
of the answer closes. Each carries its place in the article (`index` of `of`), so one that
closes out of turn is still put where it belongs. It reads; it changes nothing the writer
returns, and what it cannot read it leaves out.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from src.flow.engines.content.generation.structured_body import (
    sections_in_article_order,
    typed_section_blocks,
    typed_section_drafts,
)

logger = logging.getLogger(__name__)

# The largest answer worth reading: a writer that runs away is stopped elsewhere.
_MAX_CHARS = 400_000


# How a section a typed field writes (a how-to guide's steps) reads as a draft: its value to
# (heading, markdown), or None with nothing to show.
TypedDraft = Callable[[Any], "tuple[str, str] | None"]


def _value_end(text: str, start: int) -> int:
    """Where the value opening at ``start`` (an object, a list or a string) closes, or -1 while
    it is still being written."""
    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(text)):
        char = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                if depth == 0:
                    return position
        elif char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                return position
    return -1


class SectionStream:
    """Feed it the writer's answer piece by piece; it returns the sections that just finished.

    ``sections`` are the article's sections in the article's order, as ``(key, heading
    level)``: the answer's section fields, and the sections a typed field writes. ``typed``
    says how each of the latter reads as a draft; every other section is an object with a
    heading and its markdown.

    The answer's fields may come in any order: a section is returned when it closes, whichever
    closed before it. One the writer leaves out (an optional one, written as null) is never
    returned. When the writer is asked for its answer again, ``restart`` reads the new one
    from its start, and a section returned before is returned again as the new answer has it.
    """

    def __init__(self, sections: list[tuple[str, int]], typed: dict[str, TypedDraft] | None = None):
        self._sections = list(sections)
        self._typed = dict(typed or {})
        self._opening = [
            re.compile(
                rf'"{re.escape(key)}"\s*:\s*(?=[{{\["])'
                if key in self._typed
                else rf'"{re.escape(key)}"\s*:\s*(?={{)'
            )
            for key, _ in self._sections
        ]
        self.restart()

    def restart(self) -> None:
        """A new answer begins: nothing of the one before it is kept."""
        self._returned: set[int] = set()
        self._text = ""
        self._from = 0
        self._stopped = False

    def feed(self, piece: Any) -> list[dict]:
        if not isinstance(piece, str) or not piece or self._stopped:
            return []
        if len(self._returned) >= len(self._sections):
            return []
        if len(self._text) + len(piece) > _MAX_CHARS:
            self._stopped = True
            return []
        self._text += piece
        finished: list[dict] = []
        while len(self._returned) < len(self._sections):
            found = self._first_open()
            if found is None:
                break
            index, opens = found
            closes = _value_end(self._text, opens)
            if closes < 0:
                break
            self._returned.add(index)
            self._from = closes + 1
            section = self._read(index, self._text[opens : closes + 1])
            if section:
                finished.append(section)
        return finished

    def _first_open(self) -> tuple[int, int] | None:
        """The earliest section not yet returned whose value has opened: (its index, where)."""
        best: tuple[int, int] | None = None
        for index, opening in enumerate(self._opening):
            if index in self._returned:
                continue
            match = opening.search(self._text, self._from)
            if match and (best is None or match.end() < best[1]):
                best = (index, match.end())
        return best

    def _read(self, index: int, raw: str) -> dict | None:
        key, level = self._sections[index]
        try:
            value = json.loads(raw)
        except ValueError:
            return None
        draft = self._typed.get(key)
        if draft is not None:
            shown = draft(value)
            if not shown:
                return None
            heading, markdown = shown
        elif isinstance(value, dict):
            heading, markdown = value.get("heading"), value.get("markdown")
        else:
            return None
        if not isinstance(markdown, str) or not markdown.strip():
            return None
        return {
            "type": "section",
            "phase": "draft",
            "key": key,
            "index": index + 1,
            "of": len(self._sections),
            "level": level,
            "heading": heading.strip() if isinstance(heading, str) else "",
            "markdown": markdown.strip(),
        }


def article_section_stream(
    blocks: list | None, outline: dict, content_type: str, title: str = ""
) -> SectionStream | None:
    """The reader for one article: every section in the article's order, the answer's written
    blocks and the ones a typed field writes (a how-to guide's steps), each read as its draft.

    None when the answer has no section fields, or when the reader can't be set up: the page
    then shows the draft whole when it ends, as it did before.
    """
    if not blocks:
        return None
    try:
        drafts = typed_section_drafts(content_type, title=title)
        typed = [
            block for block in typed_section_blocks(outline, content_type) if block.key in drafts
        ]
        return SectionStream(
            [(block.key, block.level) for block in sections_in_article_order(blocks, typed)],
            typed=drafts,
        )
    except Exception:
        logger.warning("section events not set up for content_type=%s", content_type, exc_info=True)
        return None
