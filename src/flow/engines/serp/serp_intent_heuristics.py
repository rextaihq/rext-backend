"""
Heuristic filters for PAA and related searches (no LLM).
Used after competitor batch intent is known.
"""

from __future__ import annotations

import re
from typing import List

_COMMERCIAL_TOKENS = frozenset(
    {
        "best",
        "top",
        "review",
        "reviews",
        "compare",
        "comparison",
        "vs",
        "tool",
        "tools",
        "software",
        "alternative",
        "alternatives",
        "pricing",
        "cheap",
        "free",
        "buy",
        "ranked",
        "rated",
    }
)
_TRANSACTIONAL_TOKENS = frozenset(
    {
        "buy",
        "purchase",
        "price",
        "pricing",
        "cost",
        "cheap",
        "discount",
        "coupon",
        "order",
        "subscribe",
        "trial",
    }
)
_NAVIGATIONAL_TOKENS = frozenset(
    {
        "login",
        "sign",
        "official",
        "website",
        "homepage",
        "app",
    }
)
_INFORMATIONAL_PREFIXES = (
    "what is",
    "what are",
    "how does",
    "how do",
    "why does",
    "why do",
    "definition of",
    "meaning of",
    "explain",
)
_INFORMATIONAL_TOKENS = frozenset(
    {
        "how",
        "why",
        "what",
        "guide",
        "tutorial",
        "learn",
        "tips",
        "examples",
        "meaning",
        "definition",
    }
)

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "to",
        "of",
        "in",
        "on",
        "is",
    }
)


def _tokenize(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


def _query_overlap(text: str, query: str, min_shared: int = 2) -> bool:
    return len(_tokenize(text) & _tokenize(query)) >= min_shared


def _has_any(text: str, tokens: frozenset) -> bool:
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    return bool(words & tokens)


def filter_paa_for_intent(question: str, primary_intent: str, query: str) -> bool:
    """Keep PAA questions that align with the keyword's primary intent."""
    q = (question or "").strip().lower()
    if not q:
        return False

    intent = (primary_intent or "").lower()
    ql = q

    if any(ql.startswith(p) for p in _INFORMATIONAL_PREFIXES):
        return intent == "informational"

    if intent == "commercial":
        return _has_any(ql, _COMMERCIAL_TOKENS) or _query_overlap(ql, query, min_shared=1)
    if intent == "transactional":
        return _has_any(ql, _TRANSACTIONAL_TOKENS) or _query_overlap(ql, query, 1)
    if intent == "navigational":
        return _has_any(ql, _NAVIGATIONAL_TOKENS) or _query_overlap(ql, query, 1)
    if intent == "informational":
        return _has_any(ql, _INFORMATIONAL_TOKENS) or _query_overlap(ql, query, 1)
    return _query_overlap(ql, query, 1)


def filter_related_for_intent(topic: str, primary_intent: str, query: str) -> bool:
    """
    Related searches are usually same-intent; keep when they overlap the query
    or show intent-consistent modifiers.
    """
    t = (topic or "").strip().lower()
    if not t:
        return False

    intent = (primary_intent or "").lower()
    if _query_overlap(t, query, min_shared=1):
        return True

    if intent == "commercial":
        return _has_any(t, _COMMERCIAL_TOKENS)
    if intent == "transactional":
        return _has_any(t, _TRANSACTIONAL_TOKENS)
    if intent == "navigational":
        return _has_any(t, _NAVIGATIONAL_TOKENS)
    if intent == "informational":
        return _has_any(t, _INFORMATIONAL_TOKENS)

    return True


def filter_related_topics(
    topics: List[str], primary_intent: str, query: str, max_items: int = 10
) -> List[str]:
    out: List[str] = []
    for topic in topics or []:
        text = topic if isinstance(topic, str) else str(topic)
        if filter_related_for_intent(text, primary_intent, query):
            cleaned = text.strip()
            if cleaned and cleaned not in out:
                out.append(cleaned)
        if len(out) >= max_items:
            break
    return out


def filter_paa_questions(
    questions: List[str], primary_intent: str, query: str, max_items: int = 8
) -> List[str]:
    out: List[str] = []
    for question in questions or []:
        text = question if isinstance(question, str) else str(question)
        if filter_paa_for_intent(text, primary_intent, query):
            cleaned = text.strip()
            if cleaned and cleaned not in out:
                out.append(cleaned)
        if len(out) >= max_items:
            break
    return out
