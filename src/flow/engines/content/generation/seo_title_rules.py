"""Deterministic SEO title rules — the single source of truth for what makes a
title valid, shared by topic generation, content generation and validation.

Two requirements are treated as hard, not advisory:

1. The title contains the EXACT focus keyphrase the user entered.
2. The title is 50-59 characters inclusive.

The LLM is instructed to satisfy both (see prompts + the SEOTopic schema), but
an instruction is not a guarantee, so everything here is deterministic and
runs after the model. Nothing in this module invents facts, numbers, dates,
brands or claims — a deterministic repair may only re-arrange the title's own
words, add the user's own keyphrase, or append a neutral, claim-free qualifier
from a fixed ladder.
"""

from __future__ import annotations

import re
from typing import Any, Optional

TITLE_MIN_CHARS = 50
TITLE_MAX_CHARS = 59

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
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")
_SURROUNDING_QUOTES = "\"'`“”‘’ "


def normalize_title(title: Any) -> str:
    """Whitespace/quote normalization only — never changes meaning."""
    if not title:
        return ""
    text = _WHITESPACE_RE.sub(" ", str(title).strip())
    return text.strip(_SURROUNDING_QUOTES).strip()


def _normalize_for_match(text: Any) -> str:
    """Lowercase, punctuation-flattened form used for keyphrase containment.

    Padded with spaces so a containment test is implicitly word-boundary
    aware: "seo agency" must not match inside "seo agencyx".
    """
    return f" {_NON_WORD_RE.sub(' ', str(text or '').lower()).strip()} "


def contains_keyphrase(text: Any, keyphrase: Any) -> bool:
    """True when ``text`` contains the exact keyphrase as a whole-word run.

    Tolerant of casing, punctuation and whitespace differences only — a
    reordered or partial keyphrase does NOT count, because the user's
    requirement is the exact phrase.
    """
    normalized_keyphrase = _normalize_for_match(keyphrase).strip()
    if not normalized_keyphrase:
        return False
    return f" {normalized_keyphrase} " in _normalize_for_match(text)


def title_violations(title: Any, keyphrase: Any = "") -> list[str]:
    """Machine-readable reasons ``title`` is not publishable. Empty == valid."""
    cleaned = normalize_title(title)
    reasons: list[str] = []

    if not cleaned:
        return ["empty_title"]

    length = len(cleaned)
    if length < TITLE_MIN_CHARS:
        reasons.append(f"too_short:{length}")
    elif length > TITLE_MAX_CHARS:
        reasons.append(f"too_long:{length}")

    if keyphrase and not contains_keyphrase(cleaned, keyphrase):
        reasons.append("missing_focus_keyphrase")

    return reasons


def title_is_valid(title: Any, keyphrase: Any = "") -> bool:
    return not title_violations(title, keyphrase)


def _trim_to_max(title: str, keyphrase: str) -> str:
    """Drop trailing words until the title fits, never cutting the keyphrase."""
    words = title.split()
    while len(words) > 1 and len(" ".join(words)) > TITLE_MAX_CHARS:
        candidate = " ".join(words[:-1]).rstrip(" ,;:-–—")
        # Never trim away the user's keyphrase to satisfy the length rule.
        if keyphrase and not contains_keyphrase(candidate, keyphrase):
            break
        words = candidate.split()
    return " ".join(words).rstrip(" ,;:-–—")


def _pad_to_min(title: str) -> str:
    """Lift a too-short title into range with claim-free qualifiers.

    One suffix first; a very short title (~20 chars) cannot reach the minimum
    with a single suffix, so a neutral lead-in is then combined with one.
    """
    base = title.rstrip(" ,;:-–—")
    for prefix in _NEUTRAL_PREFIXES:
        for suffix in _NEUTRAL_SUFFIXES:
            candidate = f"{prefix}{base}{suffix}"
            if TITLE_MIN_CHARS <= len(candidate) <= TITLE_MAX_CHARS:
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

    if len(cleaned) > TITLE_MAX_CHARS:
        cleaned = _trim_to_max(cleaned, keyphrase)

    if len(cleaned) < TITLE_MIN_CHARS:
        cleaned = _pad_to_min(cleaned)

    return cleaned if title_is_valid(cleaned, keyphrase) else None


# NOTE: resolving WHICH keyphrase to enforce is not this module's job — that
# is ``focus_keyword.resolve_focus_keyword``, the single authority chain shared
# by outline, generation, repair and validation. This module only answers
# "given a keyphrase, is this title compliant, and can it be repaired".
