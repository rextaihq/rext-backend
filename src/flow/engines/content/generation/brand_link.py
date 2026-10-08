"""The brand's first mention linked to its approved address, in code (FB2.16, rext-control#818).

`brand_url_accuracy` asks one thing: the sentence that first names the brand links to the
approved address. That is one address in one place, yet it was handed to the repair model with
the whole article: in seven real runs a repair fixed it in 2 of 6 attempts, and in one run two
attempts were spent on it alone and both broke other checks.

So it is fixed here before the checks run, where the fix can't go wrong: a link in that
sentence that points at the brand's site under another spelling is pointed at the approved
address, and a mention with no link is given one. Anything less clear (the mention sits in a
heading, a table, a link to somewhere else) is left for the repair, as before.
"""

import logging
import re
from typing import Optional
from urllib.parse import urlsplit

from src.flow.engines.content.generation.link_integrity import normalize_url

logger = logging.getLogger(__name__)

PROSE_FIELDS = ("introduction", "body_markdown")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
# A line a link is never added to: a heading, a table row, an image or a code fence.
_NOT_PROSE_RE = re.compile(r"^\s*(#{1,6}\s|\||!\[|```|~~~)")


def _host(url: str) -> str:
    return urlsplit(url or "").netloc.lower().removeprefix("www.")


def _sentence_span(text: str, idx: int) -> tuple[int, int]:
    """Where the sentence around `idx` starts and ends: the same bounds the check reads."""
    starts = [p for p in (text.rfind("\n", 0, idx), text.rfind(". ", 0, idx)) if p != -1]
    ends = [p for p in (text.find("\n", idx), text.find(". ", idx)) if p != -1]
    return (max(starts) + 1 if starts else 0), (min(ends) if ends else len(text))


def _linked_first_mention(text: str, idx: int, name_length: int, brand_url: str) -> Optional[str]:
    """`text` with the mention at `idx` linked to `brand_url`, or None when it is right
    already or not this function's to settle."""
    start, end = _sentence_span(text, idx)
    sentence = text[start:end]
    links = list(_MD_LINK_RE.finditer(sentence))
    if any(link.group(2) == brand_url for link in links):
        return None

    # The brand's own site under another spelling (a trailing slash, http, www, a tracking
    # tag, a deeper page): the link is there, only its address is off.
    for link in links:
        url = link.group(2)
        if normalize_url(url) == normalize_url(brand_url) or _host(url) == _host(brand_url):
            at = start + link.start(2)
            return text[:at] + brand_url + text[at + len(url) :]

    # No link of the brand's in the sentence: give the mention one, where that is plainly safe.
    line_start = text.rfind("\n", 0, idx) + 1
    line_end = text.find("\n", idx)
    line = text[line_start : line_end if line_end != -1 else len(text)]
    if _NOT_PROSE_RE.match(line):
        return None
    for link in _MD_LINK_RE.finditer(line):
        if line_start + link.start() <= idx < line_start + link.end():
            return None  # the mention is another link's words or address
    if "`" in line or "](" in text[max(idx - 2, 0) : idx + name_length + 2]:
        return None
    mention = text[idx : idx + name_length]
    return f"{text[:idx]}[{mention}]({brand_url}){text[idx + name_length :]}"


def ensure_brand_link(final_content: dict, brand_context: Optional[dict], *, stage: str) -> dict:
    """`final_content` with the brand's first mention linked to its approved address."""
    brand = brand_context or {}
    name, brand_url = (
        (brand.get("brand_name") or "").strip(),
        (brand.get("brand_url") or "").strip(),
    )
    if not name or not brand_url or not final_content:
        return final_content
    # The first mention across the prose, in the order the check reads it.
    for field in PROSE_FIELDS:
        text = final_content.get(field) or ""
        idx = text.lower().find(name.lower())
        if idx == -1:
            continue
        linked = _linked_first_mention(text, idx, len(name), brand_url)
        if linked is None:
            return final_content
        logger.info("%s: the brand's first mention linked to its approved address in code", stage)
        return {**final_content, field: linked}
    return final_content
