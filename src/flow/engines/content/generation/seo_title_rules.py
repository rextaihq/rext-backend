"""Deterministic SEO title rules — the single source of truth for what makes a
title valid, shared by topic generation, content generation and validation.

Two requirements are treated as hard, not advisory:

1. The title contains the EXACT focus keyphrase the user entered.
2. The title is 50-59 characters inclusive, or up to the keyphrase plus 20 characters
   for a long keyphrase, never over 75 (``title_max_chars``).

The LLM is instructed to satisfy both (see prompts + the SEOTopic schema), but
an instruction is not a guarantee, so everything here is deterministic and
runs after the model. Nothing in this module invents facts, numbers, dates,
brands or claims — a deterministic repair may only re-arrange the title's own
words, add the user's own keyphrase, or append a neutral, claim-free qualifier
from a fixed ladder.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

TITLE_MIN_CHARS = 50
TITLE_MAX_CHARS = 59
# A long keyphrase (5-8 words, as SEO users type them) leaves 59 characters almost no room
# beside it, so its titles may run to the keyphrase plus this much, up to the ceiling. Search
# engines truncate a long title in their results; they don't reject it (G69, rext-control #585).
TITLE_ROOM_BESIDE_KEYPHRASE = 20
TITLE_MAX_CHARS_CEILING = 75

# Claim-free qualifiers used only to lift a too-short title into range. None of
# these assert a fact, a ranking, a date or a superlative, so appending one can
# never make a title untrue — which is the reason the list is fixed rather than
# model-generated.
_NEUTRAL_SUFFIXES: tuple[str, ...] = (
    ": A Complete Guide",
    ": What You Need to Know",
    ": A Practical Guide",
    ": Everything Explained",
    ": A Detailed Overview",
    ": A Step-by-Step Guide",
    ": Key Things to Know",
    " Explained in Plain English",
    ": A Complete Guide for Beginners",
)

# Neutral lead-ins, tried (empty first) only when a suffix alone cannot reach
# the minimum. Same rule as the suffixes: no facts, rankings or superlatives.
_NEUTRAL_PREFIXES: tuple[str, ...] = (
    "",
    "Understanding ",
    "A Closer Look at ",
    "A Practical Guide to ",
)

_WHITESPACE_RE = re.compile(r"\s+")
# Scripts written without spaces between words (Thai, Lao, Myanmar, Khmer, kana including the
# halfwidth forms, CJK ideographs): no space marks where their words begin and end, so a phrase's
# edge in one of them needs no space beside it, and a character of one beside a phrase is a
# boundary in itself.
_UNSPACED_SCRIPT_RE = re.compile(
    "[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    "\uf900-\ufaff\uff66-\uff9f]"
)
_SURROUNDING_QUOTES = "\"'`“”‘’ "


def _nfc(text: Any) -> str:
    """One spelling per character: an accent typed as a separate mark (NFD) is the same
    letter as its precomposed form (NFC), and counts as one character."""
    return unicodedata.normalize("NFC", str(text or ""))


def normalize_title(title: Any) -> str:
    """Whitespace/quote (and NFC) normalization only — never changes meaning."""
    if not title:
        return ""
    text = _WHITESPACE_RE.sub(" ", _nfc(title).strip())
    return text.strip(_SURROUNDING_QUOTES).strip()


def _normalize_for_match(text: Any) -> str:
    """Lowercase, punctuation-flattened form used for keyphrase containment (G69b).

    Padded with spaces so a containment test is implicitly word-boundary
    aware: "seo agency" must not match inside "seo agencyx".
    """
    # Letters, marks and digits of every script are kept (an accented letter, Arabic, Cyrillic,
    # Devanagari's vowel signs); punctuation, symbols, separators and the underscore become spaces.
    # Lowercased, not casefolded: casefolding makes different words equal ("Maße" and "Masse").
    flattened = "".join(
        " " if char == "_" or unicodedata.category(char)[0] in "PSZC" else char
        for char in _nfc(text).lower()
    )
    return f" {' '.join(flattened.split())} "


def contains_keyphrase(text: Any, keyphrase: Any) -> bool:
    """True when ``text`` contains the exact keyphrase as a whole-word run.

    Tolerant of casing, punctuation and whitespace differences only — a
    reordered or partial keyphrase does NOT count, because the user's
    requirement is the exact phrase.
    """
    phrase = _normalize_for_match(keyphrase).strip()
    if not phrase:
        return False
    haystack = _normalize_for_match(text)  # padded with a space at each end
    start = haystack.find(phrase)
    while start != -1:
        end = start + len(phrase)
        if _at_boundary(phrase[0], haystack[start - 1]) and _at_boundary(phrase[-1], haystack[end]):
            return True
        start = haystack.find(phrase, start + 1)
    return False


def _at_boundary(edge: str, beside: str) -> bool:
    """Whether a phrase's edge character ends a word against the character beside it.

    Each edge is judged on its own, so a mixed phrase ("AIツール") still needs its Latin edge
    to end a word ("XAIツール" doesn't hold it). An edge in a script without spaces needs no
    space; neither does any edge beside such a character ("最佳seo工具" holds "seo").
    """
    return (
        beside == " "
        or bool(_UNSPACED_SCRIPT_RE.match(edge))
        or bool(_UNSPACED_SCRIPT_RE.match(beside))
    )


def title_max_chars(keyphrase: Any = "") -> int:
    """The longest a title for this keyphrase may be.

    TITLE_MAX_CHARS, or the keyphrase plus TITLE_ROOM_BESIDE_KEYPHRASE when that is more,
    never over TITLE_MAX_CHARS_CEILING. A short keyphrase keeps 59.
    """
    # Measured as keyphrase_fits_a_title measures it, so a keyword the gate lets through is
    # never given a smaller limit than the gate assumed.
    length = len(_normalize_for_match(keyphrase).strip()) if keyphrase else 0
    return min(TITLE_MAX_CHARS_CEILING, max(TITLE_MAX_CHARS, length + TITLE_ROOM_BESIDE_KEYPHRASE))


def keyphrase_fits_a_title(keyphrase: Any) -> bool:
    """False when the keyphrase alone is longer than any title may be.

    Every title must contain the keyphrase and stay within TITLE_MAX_CHARS_CEILING,
    so such a keyphrase can produce no title at all: the keyword gate does not
    charge for titles then, and the topic step ends the run without a model call.
    It is measured as contains_keyphrase matches it (case, quotes and other
    punctuation flattened), so a keyword some title could hold is never refused.
    """
    return len(_normalize_for_match(keyphrase).strip()) <= TITLE_MAX_CHARS_CEILING


def title_violations(title: Any, keyphrase: Any = "") -> list[str]:
    """Machine-readable reasons ``title`` is not publishable. Empty == valid."""
    cleaned = normalize_title(title)
    reasons: list[str] = []

    if not cleaned:
        return ["empty_title"]

    length = len(cleaned)
    if length < TITLE_MIN_CHARS:
        reasons.append(f"too_short:{length}")
    elif length > title_max_chars(keyphrase):
        reasons.append(f"too_long:{length}")

    if keyphrase and not contains_keyphrase(cleaned, keyphrase):
        reasons.append("missing_focus_keyphrase")

    return reasons


def title_is_valid(title: Any, keyphrase: Any = "") -> bool:
    return not title_violations(title, keyphrase)


def _trim_to_max(title: str, keyphrase: str) -> str:
    """Drop trailing words until the title fits, never cutting the keyphrase."""
    words = title.split()
    max_chars = title_max_chars(keyphrase)
    while len(words) > 1 and len(" ".join(words)) > max_chars:
        candidate = " ".join(words[:-1]).rstrip(" ,;:-–—")
        # Never trim away the user's keyphrase to satisfy the length rule.
        if keyphrase and not contains_keyphrase(candidate, keyphrase):
            break
        words = candidate.split()
    return " ".join(words).rstrip(" ,;:-–—")


def _pad_to_min(title: str, max_chars: int = TITLE_MAX_CHARS) -> str:
    """Lift a too-short title into range with claim-free qualifiers.

    One suffix first; a very short title (~20 chars) cannot reach the minimum
    with a single suffix, so a neutral lead-in is then combined with one.
    """
    base = title.rstrip(" ,;:-–—")
    for prefix in _NEUTRAL_PREFIXES:
        for suffix in _NEUTRAL_SUFFIXES:
            candidate = f"{prefix}{base}{suffix}"
            if TITLE_MIN_CHARS <= len(candidate) <= max_chars:
                return candidate
    return title


def repair_title(title: Any, keyphrase: Any = "") -> Optional[str]:
    """Best-effort deterministic repair. Returns None when it cannot comply.

    Applied only as the last net, after the LLM repair pass has already been
    given a chance — see ``topic_generation._repair_invalid_titles``. Returning
    None is meaningful: the caller keeps the previous valid value rather than
    showing the user something that breaks the rule.
    """
    cleaned = normalize_title(title)
    keyphrase = normalize_title(keyphrase)

    if not cleaned and not keyphrase:
        return None

    # Missing keyphrase: lead with it, which is also the placement SEO wants.
    if keyphrase and not contains_keyphrase(cleaned, keyphrase):
        # Capitalized for display only; matching is case-insensitive, so the
        # title still contains the user's exact phrase.
        lead = " ".join(word[:1].upper() + word[1:] for word in keyphrase.split())
        cleaned = f"{lead}: {cleaned}" if cleaned else lead

    if len(cleaned) > title_max_chars(keyphrase):
        cleaned = _trim_to_max(cleaned, keyphrase)

    if len(cleaned) < TITLE_MIN_CHARS:
        cleaned = _pad_to_min(cleaned, title_max_chars(keyphrase))

    return cleaned if title_is_valid(cleaned, keyphrase) else None


def keyphrase_title(keyphrase: Any) -> Optional[str]:
    """The keyphrase itself as a title, when no generated title survives (G69).

    Title-cased for display (matching is case-insensitive, so it still holds the exact
    phrase), and lifted to the minimum length with a claim-free qualifier as any repair is.
    None when even that breaks the rules (a keyphrase whose punctuation takes it over the
    limit, or one no qualifier lifts to the minimum): an invalid title is never offered.
    """
    keyphrase = normalize_title(keyphrase)
    if not keyphrase:
        return None
    title = " ".join(word[:1].upper() + word[1:] for word in keyphrase.split())
    return repair_title(title, keyphrase)


# NOTE: resolving WHICH keyphrase to enforce is not this module's job — that
# is ``focus_keyword.resolve_focus_keyword``, the single authority chain shared
# by outline, generation, repair and validation. This module only answers
# "given a keyphrase, is this title compliant, and can it be repaired".
