"""Shared vocabulary for PRODUCT/TOOL NAMES on comparison-style content types.

A comparison page is only worth publishing if the things it compares are real.
The failure this module exists to stop is the outline model inventing
placeholder entities — "Agency A", "Agency B", "Tool 1" — when it is handed a
topic but no actual product names, and every downstream stage then faithfully
writing an article about companies that do not exist.

Three consumers share the definitions here, deliberately in one place:

  * the outline SCHEMAS, which state the rule on the field itself, so it is
    read at the moment the name is decoded rather than a thousand tokens
    earlier in the prompt;
  * `brand_slot`, which treats a placeholder-named product as an empty slot the
    approved brand may take over, instead of a real competitor it must protect;
  * `validation`, which reports any placeholder that still reached the article.

Detection is deliberately conservative. A false positive here deletes a real
competitor from a comparison, which is worse than the placeholder it was trying
to catch, so the patterns match only names that carry no identity at all — a
generic category noun plus a positional marker, or a known dummy token.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# Category nouns that name a KIND of thing rather than a specific one. A real
# product name may CONTAIN one of these ("Zoho CRM Tool"); only a name that is
# nothing but one of these plus a position marker is a placeholder.
_CATEGORY_NOUN = (
    r"(?:agency|agencies|tool|product|brand|option|vendor|company|platform|"
    r"service|solution|software|provider|competitor|alternative|app|suite|"
    r"system|choice|pick|candidate)"
)

# Position markers: a single letter, a small number, or a spelled-out ordinal.
_POSITION = r"(?:[a-z]|\d{1,2}|one|two|three|four|five|first|second|third|fourth|fifth)"

_PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "Agency A", "Tool 1", "Product One", "Option #2", "Vendor-B"
    re.compile(rf"^{_CATEGORY_NOUN}\s*[#\-]?\s*{_POSITION}$", re.IGNORECASE),
    # "A Tool", "1st Product" — the same thing with the marker leading.
    re.compile(rf"^{_POSITION}\s+{_CATEGORY_NOUN}$", re.IGNORECASE),
    # "Your Brand", "Our Product", "The Company"
    re.compile(
        r"^(?:your|our|the|my)\s+(?:brand|company|product|tool|agency|platform|service)$",
        re.IGNORECASE,
    ),
    # "Product Name", "Tool Here", "Brand X"
    re.compile(rf"^{_CATEGORY_NOUN}\s+(?:name|here|xyz|x|y|z)$", re.IGNORECASE),
    # Classic dummy tokens.
    re.compile(
        r"^(?:acme(?:\s+\w+)?|example(?:\s*corp\w*)?|examplecorp|foo|bar|baz|lorem|"
        r"ipsum|placeholder|tbd|todo|n/?a|xyz\s*(?:corp|inc|co)?)$",
        re.IGNORECASE,
    ),
    # Bracketed/templated leftovers: "[Brand]", "{product}", "<Tool>"
    re.compile(r"^[\[\{<].+[\]\}>]$"),
)

# Injected verbatim into schema field descriptions and outline prompts, so the
# rule the model reads and the rule the code enforces are the same sentence.
PRODUCT_NAME_GUIDANCE = (
    "Use the REAL, specific, publicly recognisable name of an actual product, tool or "
    "company (e.g. 'Ahrefs', 'HubSpot'). NEVER invent a generic stand-in such as "
    "'Agency A', 'Agency B', 'Tool 1', 'Product A', 'Competitor X', 'Your Brand' or "
    "'Acme Corp' — a placeholder name makes the entire comparison worthless. If you do "
    "not know enough real named products to fill every slot, compare FEWER products "
    "rather than inventing one."
)


def is_placeholder_product_name(name: Any) -> bool:
    """True when `name` is a generic stand-in rather than a real product.

    Non-strings and blanks count as placeholders: an unnamed product is no more
    usable in a comparison than a fake one, and both should be treated as a free
    slot rather than as a competitor worth protecting.
    """
    if not isinstance(name, str):
        return False if name is None else True
    stripped = name.strip()
    if not stripped:
        return True
    # Collapse internal whitespace so "Agency   A" matches like "Agency A".
    collapsed = re.sub(r"\s+", " ", stripped)
    return any(pattern.match(collapsed) for pattern in _PLACEHOLDER_PATTERNS)


# Scanning counterpart to the patterns above, for finding a placeholder inside
# PROSE rather than validating a standalone field.
#
# Capitalisation is required on both halves, and that is load-bearing rather
# than cosmetic: a placeholder reaches the reader as a proper noun ("Agency A
# charges more"), while the same words uncapitalised are ordinary English ("the
# tool a beginner needs"). Matching case-insensitively here would flag correct
# sentences in every article that happens to use the word "tool".
_PLACEHOLDER_IN_TEXT_RE = re.compile(
    r"\b(?:Agency|Agencies|Tool|Product|Brand|Option|Vendor|Company|Platform|Service|"
    r"Solution|Software|Provider|Competitor|Alternative|App|Suite|System)"
    r"\s*[#\-]?\s*"
    r"(?:[A-Z]|\d{1,2}|One|Two|Three|Four|Five)\b"
)


def find_placeholder_names_in_text(text: str) -> list[str]:
    """Placeholder entity names appearing in finished prose, de-duplicated.

    Used by validation to report a fabricated competitor that survived into the
    article. Reporting, not repair: the correct name is not knowable at that
    point, so inventing a replacement would swap one fabrication for another.
    """
    if not isinstance(text, str) or not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in _PLACEHOLDER_IN_TEXT_RE.finditer(text):
        phrase = " ".join(match.group(0).split())
        key = phrase.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append(phrase)
    return found


def find_placeholder_names(names: Iterable[Any]) -> list[str]:
    """Every placeholder in `names`, in order, de-duplicated case-insensitively."""
    found: list[str] = []
    seen: set[str] = set()
    for name in names:
        if not is_placeholder_product_name(name):
            continue
        text = str(name).strip()
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(text)
    return found
