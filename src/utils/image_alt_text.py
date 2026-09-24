"""Alt text for published images — a single, shared derivation.

A manually uploaded image is arbitrary: the system has no idea what it
depicts. So alt text is never *described* here, only *attributed* — it says
what the image belongs to (this article, this topic), which is true no matter
what the user uploaded, rather than claiming something is visible in it.

Priority, highest first:

1. Alt text the user (or the content agent) explicitly provided — returned
   as-is. An explicit choice is never second-guessed or "improved".
2. The article title, when it already contains the focus keyphrase.
3. ``"<focus keyphrase> — <title>"``, when the title does not contain the
   keyphrase. The keyphrase appears exactly once; this is what makes the
   image count toward Yoast's keyphrase-in-alt check without stuffing.
4. Whichever of title / keyphrase exists on its own.
5. ``None`` — better no alt attribute than an invented description.

The image *filename* is deliberately not a source: uploads are typically
``IMG_2043.jpg``, which is noise rather than topic.
"""

from __future__ import annotations

import html
import re
from typing import Optional

# Accessibility guidance puts a practical ceiling around 125 characters —
# past that, screen readers are being read an essay instead of a label.
MAX_ALT_TEXT_LENGTH = 125

_HTML_TAG_RE = re.compile(r"<[^>]+>")
# Markdown emphasis/code/heading marks that would be read aloud literally.
_MARKDOWN_MARKS_RE = re.compile(r"[*_`#]+")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean(value: Optional[str]) -> str:
    """Flatten a title/keyphrase into plain single-line text."""
    if not value:
        return ""
    text = html.unescape(str(value))
    text = _HTML_TAG_RE.sub(" ", text)
    text = _MARKDOWN_MARKS_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def _truncate(text: str, limit: int = MAX_ALT_TEXT_LENGTH) -> str:
    """Shorten to ``limit`` characters on a word boundary, without an ellipsis."""
    if len(text) <= limit:
        return text
    clipped = text[:limit].rstrip()
    if " " in clipped:
        clipped = clipped[: clipped.rfind(" ")]
    return clipped.rstrip(" ,;:-–—")


def build_image_alt_text(
    user_alt: Optional[str] = None,
    title: Optional[str] = None,
    focus_keyphrase: Optional[str] = None,
) -> Optional[str]:
    """Best available alt text for an image published with an article.

    Returns None when there is nothing truthful to say — callers must then
    leave the alt attribute alone rather than substituting a placeholder.
    """
    explicit = _clean(user_alt)
    if explicit:
        return _truncate(explicit)

    clean_title = _clean(title)
    clean_keyphrase = _clean(focus_keyphrase)

    if clean_title and clean_keyphrase:
        if clean_keyphrase.lower() in clean_title.lower():
            # The title already carries the keyphrase — repeating it would be
            # stuffing, and the title reads more naturally on its own.
            return _truncate(clean_title)
        return _truncate(f"{clean_keyphrase} — {clean_title}")

    if clean_title:
        return _truncate(clean_title)
    if clean_keyphrase:
        return _truncate(clean_keyphrase)
    return None
