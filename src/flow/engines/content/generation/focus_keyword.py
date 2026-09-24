"""Single source of truth for the article's focus keyword.

The focus keyword is the USER'S OWN query — the phrase they typed or picked at
the keyword-selection step. It is never rewritten, re-cased, shortened or
re-invented by a model anywhere in the pipeline.

Before this module existed the keyword was effectively re-derived at every
stage: `generate_outline` let the outline LLM invent its own `focus_keyphrase`
(the schema literally asks for "2-4 words recommended"), `generate_content`
built its prompt from `keywords_to_include[0]`, `build_requirements_spec`
validated against whatever the outline had invented, and `generate_content`
then stamped the user's real keyword onto the finished payload at the very
end. That last step is a label swap, not optimization: the article had already
been written for a different phrase, so the phrase actually reported as the
focus keyphrase was under-represented in the body by construction.

Resolution is an authority chain, not a guess — the earliest entry that holds
a non-empty value wins, and every consumer calls the same function so the
stages cannot disagree with each other.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# State key the pinned keyword is carried under, inside `content`.
FOCUS_KEYWORD_STATE_KEY = "focus_keyword"

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_focus_keyword(value: Any) -> str:
    """Trim and collapse internal whitespace — nothing else.

    Deliberately NOT lowercasing, de-pluralizing, stripping punctuation or
    reordering words: the requirement is that the focus keyword remains
    character-for-character the user's query. Whitespace normalization only
    removes artifacts of transport (a trailing newline from a textarea, a
    double space from a paste), which no user meant to type.
    """
    if not isinstance(value, str):
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


def _first_non_empty(*candidates: Any) -> str:
    for candidate in candidates:
        normalized = normalize_focus_keyword(candidate)
        if normalized:
            return normalized
    return ""


def focus_keyword_from_outline(outline: Optional[dict]) -> str:
    """The keyword pinned onto an outline, if one was pinned.

    Reads the same nested shapes `render._resolve_focus_keyphrase` handles,
    because a handful of outline schemas nest their SEO block rather than
    exposing `focus_keyphrase` at the top level.
    """
    outline = outline or {}
    direct = normalize_focus_keyword(outline.get("focus_keyphrase"))
    if direct:
        return direct
    for wrapper in ("seo", "seo_plan"):
        nested = outline.get(wrapper)
        if isinstance(nested, dict):
            value = normalize_focus_keyword(nested.get("focus_keyphrase"))
            if value:
                return value
    return ""


def resolve_focus_keyword(state: Optional[dict]) -> str:
    """The one focus keyword for this run, resolved from graph state.

    Authority order, highest first:

    1. ``content.focus_keyword``    — already pinned earlier in this same run.
    2. ``seo_result.keyword_recommendations.selected_keyword`` — what the user
       confirmed at the keyword-selection interrupt. The most explicit signal
       there is.
    3. ``serp_payload.query``       — the raw query the run started from; also
       what the keyword-selection node writes back, so it agrees with (2) when
       both exist. Covers library/bulk runs that skip keyword selection.
    4. ``serp_normalized.query``    — normalized SERP echo of the same query.
    5. ``outline.focus_keyphrase``  — model-invented; a last resort that keeps
       older/partial states working rather than returning nothing.
    6. ``content.selected_topic``   — final fallback so a keyword always exists.

    Returns "" only when the state carries no usable value at all; callers
    treat that as "skip keyword enforcement", never as a reason to invent one.
    """
    state = state or {}
    content_state = state.get("content") or {}
    seo_result = state.get("seo_result") or {}
    recommendations = seo_result.get("keyword_recommendations") or {}

    return _first_non_empty(
        content_state.get(FOCUS_KEYWORD_STATE_KEY),
        recommendations.get("selected_keyword"),
        (state.get("serp_payload") or {}).get("query"),
        (state.get("serp_normalized") or {}).get("query"),
        focus_keyword_from_outline(content_state.get("outline")),
        content_state.get("selected_topic"),
    )


def pin_focus_keyword(outline: dict, focus_keyword: str) -> dict:
    """Stamp the resolved keyword onto an outline dict, in place.

    Applied as soon as the outline exists so that everything built FROM the
    outline downstream — the generation prompt, `build_requirements_spec`, the
    density check, internal-link and brand-voice relevance search — is working
    from the user's phrase rather than the model's substitute.

    Also ensures the keyword leads `keywords_to_include`: `generate_content`
    derives its "Primary Keyword" prompt line from that list's first entry, so
    pinning `focus_keyphrase` alone would leave the writer model still being
    told to optimize for something else.
    """
    keyword = normalize_focus_keyword(focus_keyword)
    if not outline or not keyword:
        return outline

    previous = focus_keyword_from_outline(outline)
    if previous and previous.lower() != keyword.lower():
        logger.info(
            "pin_focus_keyword: replacing model-generated focus_keyphrase %r with user keyword %r",
            previous,
            keyword,
        )

    outline["focus_keyphrase"] = keyword
    # Keep nested copies consistent — some schemas expose the SEO block instead
    # of (or alongside) the top-level field, and a stale nested value would win
    # for any consumer that reads the nested shape first.
    for wrapper in ("seo", "seo_plan"):
        nested = outline.get(wrapper)
        if isinstance(nested, dict) and "focus_keyphrase" in nested:
            nested["focus_keyphrase"] = keyword

    existing = [
        str(k).strip() for k in (outline.get("keywords_to_include") or []) if str(k).strip()
    ]
    deduped = [k for k in existing if k.lower() != keyword.lower()]
    outline["keywords_to_include"] = [keyword, *deduped]

    return outline
