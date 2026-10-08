"""The brand's first mention linked to its approved address, in code (FB2.16, rext-control#818).

`brand_url_accuracy` asks one thing: the sentence that first names the brand links to the
approved address. That is one address in one place, yet it was handed to the repair model with
the whole article: in seven real runs a repair fixed it in 2 of 6 attempts, and in one run two
attempts were spent on it alone and both broke other checks.

So it is fixed here before the checks run, in the two cases where the fix can't go wrong:

- the brand's name is the whole of a link's words and that link points at the brand's site
  under another spelling: the link is pointed at the approved address;
- the brand's name stands in plain prose as a word of its own, written as the brand writes
  it: it is given the link.

Everything else is left for the repair, as before: a name inside another word or an address,
an ordinary word that only spells like the brand ("later" for Later), a name in a heading, a
table, an image or code, or among the words of another link. No other link is touched.
"""

import logging
import re
from typing import Optional
from urllib.parse import urlsplit

from src.flow.engines.content.generation.link_integrity import normalize_url

logger = logging.getLogger(__name__)

PROSE_FIELDS = ("introduction", "body_markdown")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
# A line a link is never added to: a heading, a table row or an image.
_NOT_PROSE_RE = re.compile(r"^\s*(#{1,6}\s|\||!\[)")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_OPENS = "(\"'“‘"
_CLOSES = ".,;:!?)\"'’”"


def _host(url: str) -> str:
    return urlsplit(url or "").netloc.lower().removeprefix("www.")


def _sentence_span(text: str, idx: int) -> tuple[int, int]:
    """Where the sentence around `idx` starts and ends: the same bounds the check reads."""
    starts = [p for p in (text.rfind("\n", 0, idx), text.rfind(". ", 0, idx)) if p != -1]
    ends = [p for p in (text.find("\n", idx), text.find(". ", idx)) if p != -1]
    return (max(starts) + 1 if starts else 0), (min(ends) if ends else len(text))


def _a_word_of_its_own(text: str, idx: int, length: int) -> bool:
    """Whether the name at `idx` is the brand named, not letters inside something else:
    "buffering" for Buffer, or the name inside a bare address ("https://nextly.test/docs")."""
    before = text[idx - 1] if idx else " "
    if not (before.isspace() or before in _OPENS):
        return False
    after = text[idx + length : idx + length + 2]
    if not after or after[0].isspace() or after.lower() in ("'s", "’s"):
        return True
    return after[0] in _CLOSES and (len(after) == 1 or not after[1].isalnum())


def _in_code(text: str, idx: int) -> bool:
    """Whether `idx` is on a line with inline code, or inside a fenced block."""
    line_start = text.rfind("\n", 0, idx) + 1
    line_end = text.find("\n", idx)
    if "`" in text[line_start : line_end if line_end != -1 else len(text)]:
        return True
    fenced = False
    for line in text[:line_start].splitlines():
        if _FENCE_RE.match(line):
            fenced = not fenced
    return fenced


def _linked_first_mention(text: str, idx: int, name: str, brand_url: str) -> Optional[str]:
    """`text` with the mention at `idx` linked to `brand_url`, or None when it is right
    already or not this function's to settle."""
    length = len(name)
    start, end = _sentence_span(text, idx)
    if any(link.group(2) == brand_url for link in _MD_LINK_RE.finditer(text[start:end])):
        return None

    line_start = text.rfind("\n", 0, idx) + 1
    line_end = text.find("\n", idx)
    line = text[line_start : line_end if line_end != -1 else len(text)]
    if _NOT_PROSE_RE.match(line) or _in_code(text, idx):
        return None

    for link in _MD_LINK_RE.finditer(line):
        if not line_start + link.start() <= idx < line_start + link.end():
            continue
        # The name is inside this link. When it is all of the link's words and the link
        # points at the brand's site under another spelling (a trailing slash, http, www, a
        # tracking tag, a deeper page), only its address is off.
        url = link.group(2)
        its_words = link.group(1).strip().lower() == text[idx : idx + length].lower()
        if its_words and (
            normalize_url(url) == normalize_url(brand_url) or _host(url) == _host(brand_url)
        ):
            at = line_start + link.start(2)
            return text[:at] + brand_url + text[at + len(url) :]
        return None  # among another link's words, or part of a link's address

    mention = text[idx : idx + length]
    if mention != name or not _a_word_of_its_own(text, idx, length):
        return None
    return f"{text[:idx]}[{mention}]({brand_url}){text[idx + length :]}"


def ensure_brand_link(final_content: dict, brand_context: Optional[dict], *, stage: str) -> dict:
    """`final_content` with the brand's first mention linked to its approved address."""
    brand = brand_context or {}
    name = (brand.get("brand_name") or "").strip()
    brand_url = (brand.get("brand_url") or "").strip()
    if not name or not brand_url or not final_content:
        return final_content
    # The first mention across the prose, as the check reads it: the first place the name's
    # letters appear, whatever surrounds them.
    for field in PROSE_FIELDS:
        text = final_content.get(field) or ""
        idx = text.lower().find(name.lower())
        if idx == -1:
            continue
        linked = _linked_first_mention(text, idx, name, brand_url)
        if linked is None:
            return final_content
        logger.info("%s: the brand's first mention linked to its approved address in code", stage)
        return {**final_content, field: linked}
    return final_content
