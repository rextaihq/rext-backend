"""
One "no script or markup" rule for text a person types into the sign-up and
sign-in forms (name, email, password, confirm password).

Rejected anywhere in the value:
- "<" or ">", so no HTML or script tag can be entered
- a script URL scheme such as "javascript:" or "vbscript:"
- control characters and invisible characters (zero-width spaces, bidi
  overrides) that make a value look different from what it is

This is input hygiene on top of, not instead of, the real protections:
queries are parameterised by SQLAlchemy, passwords are only stored as
bcrypt hashes, and output is escaped where it is rendered.
"""

import re

# "<", ">", C0 controls and DEL, zero-width spaces/joiners and directional
# marks (U+200B-U+200F), bidi overrides (U+202A-U+202E), word joiner and
# bidi isolates (U+2060-U+2069), and the byte-order mark (U+FEFF).
_MARKUP_OR_HIDDEN_CHARS_RE = re.compile(
    "[<>\\x00-\\x1f\\x7f\\u200b-\\u200f\\u202a-\\u202e\\u2060-\\u2069\\ufeff]"
)
_SCRIPT_SCHEME_RE = re.compile(r"(java|vb)script\s*:", re.IGNORECASE)


def find_script_content(value: str, label: str) -> str | None:
    """The message for a value containing script/markup, or None if it is clean."""
    if _MARKUP_OR_HIDDEN_CHARS_RE.search(value):
        return f"{label} cannot contain < or >, HTML/script tags, or hidden characters"
    if _SCRIPT_SCHEME_RE.search(value):
        return f"{label} cannot contain script code such as 'javascript:'"
    return None


def reject_script_content(value, label: str):
    """Pydantic-friendly check: returns the value, raises ValueError if unsafe.

    Non-string values are returned untouched for the field's own type check.
    """
    if isinstance(value, str):
        message = find_script_content(value, label)
        if message:
            raise ValueError(message)
    return value
