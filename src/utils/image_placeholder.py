"""Manual-upload image placeholder — shared constant + helpers.

When image generation is disabled (Settings.AI_IMAGE_GENERATION_ENABLED is
False), the content agent still runs the full image *planning* pipeline —
art direction, composition, alt text — but never calls the paid image model.
Instead of a real image URL, it embeds a placeholder using this custom URI
scheme as ordinary markdown image syntax, e.g.:

    ![Featured image for X](rext-placeholder:3f9c1e2a-...)

The admin frontend's editor recognizes the `rext-placeholder:` scheme and
renders an "upload image here" slot instead of an `<img>` — letting the user
manually upload an image at the spot the pipeline suggested, or dismiss it
and publish with no image at all.

This placeholder must NEVER reach a live page: it is not a real, fetchable
URL, so an unresolved one left in body_markdown/body_html would render as a
broken image. Every publish call site (WordPress, Shopify, ...) MUST run
`strip_unresolved_placeholders` on body text immediately before sending it
to the destination site.
"""

from __future__ import annotations

import re

# Deliberately not http(s) — this keeps the placeholder outside of every
# regex/heuristic downstream code already uses to detect "a real image URL"
# (WordPress's featured-image and embedded-image sync both require
# https?://), so an unresolved placeholder is never mistaken for one.
PLACEHOLDER_SCHEME = "rext-placeholder:"

# Matches the markdown image syntax produced by build_placeholder_marker,
# including the optional `"title"` suffix the frontend editor's markdown
# exporter adds when round-tripping the node (![alt](src "title")).
_PLACEHOLDER_MD_RE = re.compile(
    r"!\[[^\]]*\]\(" + re.escape(PLACEHOLDER_SCHEME) + r'[^)\s"]*(?:\s+"[^"]*")?\)'
)
# Matches the rendered HTML form (<img src="rext-placeholder:...">), in case
# body_html (rather than body_markdown) is what reaches a publish call site.
_PLACEHOLDER_HTML_RE = re.compile(
    r'<img\b[^>]*\bsrc=["\']' + re.escape(PLACEHOLDER_SCHEME) + r'[^"\']*["\'][^>]*/?>'
)


def build_placeholder_marker(alt_text: str, placeholder_id: str) -> str:
    """Markdown image syntax for a manual-upload placeholder."""
    safe_alt = (alt_text or "Suggested image").replace("[", "").replace("]", "").strip()
    return f"![{safe_alt}]({PLACEHOLDER_SCHEME}{placeholder_id})"


def strip_unresolved_placeholders(text: str | None) -> str | None:
    """Remove any manual-upload placeholder left unresolved by the user.

    Safe to call on markdown or HTML (or None); a no-op when nothing matches.
    Call this on body text immediately before it is sent to any publish
    destination, so a placeholder the user never acted on can never become a
    broken image on a live page.
    """
    if not text:
        return text
    cleaned = _PLACEHOLDER_MD_RE.sub("", text)
    cleaned = _PLACEHOLDER_HTML_RE.sub("", cleaned)
    if cleaned != text:
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned
