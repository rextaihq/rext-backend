"""The article's sections, read out of the writer's answer while it is still being written.

The writer answers once, with one field per section, and the answer arrives in pieces. The
page was looking in those pieces for `body_markdown`, which is only put together after the
answer ends, so no text showed for the whole wait (rext-control#773). A measured run: the
sections arrive from 27 to 45 seconds after approval, one every 2 to 3 seconds, and the
finished article at 171.

`SectionStream` is fed the pieces as they come and returns each section the moment its part
of the answer closes, in the order the outline has them. It reads; it changes nothing the
writer returns, and what it cannot read it leaves out.
"""

from __future__ import annotations

import json
import re
from typing import Any

# The largest answer worth reading: a writer that runs away is stopped elsewhere.
_MAX_CHARS = 400_000


def _closing_brace(text: str, start: int) -> int:
    """Where the object opening at ``start`` closes, or -1 while it is still being written."""
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
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return position
    return -1


class SectionStream:
    """Feed it the writer's answer piece by piece; it returns the sections that just finished.

    ``sections`` are the answer's section fields in the outline's order, as
    ``(key, heading level)``. A section the writer leaves out (an optional one, written as
    null) is passed over when a later one arrives.
    """

    def __init__(self, sections: list[tuple[str, int]]):
        self._sections = list(sections)
        self._next = 0
        self._text = ""
        self._from = 0

    def feed(self, piece: Any) -> list[dict]:
        if not isinstance(piece, str) or not piece or self._next >= len(self._sections):
            return []
        if len(self._text) + len(piece) > _MAX_CHARS:
            self._next = len(self._sections)
            return []
        self._text += piece
        finished: list[dict] = []
        while self._next < len(self._sections):
            found = self._first_open()
            if found is None:
                break
            index, opens = found
            closes = _closing_brace(self._text, opens)
            if closes < 0:
                break
            self._next = index + 1
            self._from = closes + 1
            section = self._read(index, self._text[opens : closes + 1])
            if section:
                finished.append(section)
        return finished

    def _first_open(self) -> tuple[int, int] | None:
        """The earliest section not yet returned whose object has opened: (its index, where)."""
        best: tuple[int, int] | None = None
        for index in range(self._next, len(self._sections)):
            key = re.escape(self._sections[index][0])
            match = re.compile(rf'"{key}"\s*:\s*\{{').search(self._text, self._from)
            if match and (best is None or match.end() - 1 < best[1]):
                best = (index, match.end() - 1)
        return best

    def _read(self, index: int, raw: str) -> dict | None:
        try:
            block = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(block, dict):
            return None
        markdown = block.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            return None
        heading = block.get("heading")
        key, level = self._sections[index]
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
