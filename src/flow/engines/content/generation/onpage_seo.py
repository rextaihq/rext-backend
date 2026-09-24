"""Deterministic content-level on-page SEO enforcement.

One function, ``enforce_onpage_seo``, is applied at the end of every node that
can mutate ``content.final_content`` (generation, repair, humanization, final
validation). It guarantees four things the LLM is asked for but cannot be
trusted to deliver every time:

1. ``title`` is EXACTLY the title the user selected.
2. ``meta_description`` exists, contains the exact focus keyphrase, and is
   never longer than ``META_DESCRIPTION_MAX_CHARS`` (156) characters.
3. ``introduction`` contains the exact focus keyphrase.
4. ``focus_keyphrase`` is the user's keyphrase, not the model's own.

It is a repair layer, not the primary mechanism: the prompts and the
deterministic checks in ``validation.py`` give the model its chance first, and
the repair loop runs before this ever has to synthesize anything. It never
touches ``body_markdown`` -- rewriting prose deterministically would do more
harm than the problem it fixes, so a body-level mismatch is reported by
validation and repaired by the LLM instead.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.flow.engines.content.generation.seo_title_rules import (
    contains_keyphrase,
    normalize_title,
)

logger = logging.getLogger(__name__)

# Yoast's meta-description length assessment is green between 120 and 156
# characters: below 120 is "too short", above 156 is truncated in the SERP. The
# ceiling was previously 160, so every "140-160" answer the model gave in its
# top four characters shipped over Yoast's limit.
META_DESCRIPTION_MIN_CHARS = 120
META_DESCRIPTION_MAX_CHARS = 140

# Clause boundaries a too-long description may be cut back to. Punctuation-led
# only: cutting at a conjunction ("and", "with") too often leaves a dangling
# half-thought, whereas text before a comma or dash is usually a complete claim.
_CLAUSE_BOUNDARY_RE = re.compile(r"(?:[,;:]|\s[–—-])\s")
_TRAILING_JOINERS = " ,;:-–—("

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN_NOISE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)|\[([^\]]*)\]\([^)]*\)|[#*_`>|]")
_WHITESPACE_RE = re.compile(r"\s+")


def _plain_text(markdown: Optional[str]) -> str:
    """Markdown stripped down to readable prose, for excerpting only."""
    text = _MARKDOWN_NOISE_RE.sub(r"\1", markdown or "")
    return _WHITESPACE_RE.sub(" ", text).strip()


def _first_sentences(text: str, limit: int) -> str:
    """Whole sentences from ``text`` up to ``limit`` characters."""
    out = ""
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{out} {sentence}".strip()
        if len(candidate) > limit:
            break
        out = candidate
    return out


def build_meta_description(
    *,
    focus_keyphrase: str,
    title: str,
    introduction: str = "",
    body_markdown: str = "",
) -> str:
    """Synthesize a compliant meta description from content that already exists.

    Deliberately extractive: the sentences come from the article's own
    introduction or body, so nothing is asserted that the article does not
    already say. Only the leading keyphrase clause and the closing CTA are
    added, and neither states a fact. Every branch is length-budgeted, so the
    result is never longer than ``META_DESCRIPTION_MAX_CHARS`` and is never cut
    mid-word.
    """
    keyphrase = normalize_title(focus_keyphrase)
    source = _plain_text(introduction) or _plain_text(body_markdown) or normalize_title(title)
    cta = " Read the full guide."

    # A "Keyphrase: ..." lead is only needed when the article's own opening
    # sentences do not already name the keyphrase.
    lead = f"{keyphrase[:1].upper()}{keyphrase[1:]}: " if keyphrase else ""
    opening = _first_sentences(source, META_DESCRIPTION_MAX_CHARS - len(cta))
    if keyphrase and opening and contains_keyphrase(opening, keyphrase):
        lead = ""

    budget = META_DESCRIPTION_MAX_CHARS - len(lead) - len(cta)
    if budget < 40:
        # A keyphrase so long it leaves little room: drop the CTA before
        # dropping the article's own words.
        cta = ""
        budget = META_DESCRIPTION_MAX_CHARS - len(lead)

    excerpt = _first_sentences(source, budget) or _trim_to_word_boundary(source, budget)
    description = f"{lead}{excerpt}{cta}".strip()

    # Extend only when the first sentences were too thin to reach the minimum,
    # and only with further WHOLE sentences from the same source.
    if len(description) < META_DESCRIPTION_MIN_CHARS and excerpt and source.startswith(excerpt):
        remainder = source[len(excerpt) :].strip()
        room = META_DESCRIPTION_MAX_CHARS - len(description) - 1
        extra = _first_sentences(remainder, room) if remainder and room > 0 else ""
        if extra:
            description = f"{lead}{excerpt} {extra}{cta}".strip()

    if len(description) > META_DESCRIPTION_MAX_CHARS:  # defensive; the budgets prevent it
        description = _trim_to_word_boundary(description, META_DESCRIPTION_MAX_CHARS)

    return description.strip()


def _trim_to_word_boundary(text: str, limit: int) -> str:
    """``text`` cut back to whole words, at most ``limit`` characters.

    The last-resort cut, used only where no sentence or clause boundary fits.
    Never splits a word, and closes with a single ellipsis character so the
    result does not pose as a complete sentence.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 1:
        return ""
    head = text[: limit - 1]
    if text[limit - 1] != " " and " " in head:
        head = head.rsplit(" ", 1)[0]
    head = head.rstrip(_TRAILING_JOINERS + ".")
    return f"{head}…" if head else ""


def shorten_meta_description(description: str, focus_keyphrase: str = "") -> Optional[str]:
    """Bring an over-long description within the limit WITHOUT blind truncation.

    Tries, in order, the options that keep the writer's own text meaningful:

    1. Whole sentences — the best in-order subset of the description's own
       sentences that fits, reaches the minimum length, keeps the focus
       keyphrase and, where possible, keeps the closing call to action.
    2. A clause cut — the longest prefix ending at a comma/semicolon/colon/dash
       boundary that fits, reaches the minimum and keeps the keyphrase, closed
       as a sentence.

    Returns None when neither yields a compliant description; the caller then
    rebuilds one extractively from the article.
    """
    text = normalize_title(description)
    keyphrase = normalize_title(focus_keyphrase)
    if len(text) <= META_DESCRIPTION_MAX_CHARS:
        return text

    def _acceptable(candidate: str) -> bool:
        return META_DESCRIPTION_MIN_CHARS <= len(candidate) <= META_DESCRIPTION_MAX_CHARS and (
            not keyphrase or contains_keyphrase(candidate, keyphrase)
        )

    # 1. Whole-sentence subsets, order preserved. Descriptions are a handful of
    #    sentences, so exhaustive search is tiny.
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if 1 < len(sentences) <= 6:
        count = len(sentences)
        best: Optional[tuple[tuple[bool, int], str]] = None
        for mask in range(1, 1 << count):
            candidate = " ".join(sentences[i] for i in range(count) if mask & (1 << i))
            if not _acceptable(candidate):
                continue
            rank = (bool(mask & (1 << (count - 1))), len(candidate))
            if best is None or rank > best[0]:
                best = (rank, candidate)
        if best is not None:
            return best[1]

    # 2. Clause cut, longest first.
    for match in reversed(list(_CLAUSE_BOUNDARY_RE.finditer(text))):
        candidate = text[: match.start()].rstrip(_TRAILING_JOINERS + ".") + "."
        if _acceptable(candidate):
            return candidate

    return None


def fit_meta_description(
    description: str,
    *,
    focus_keyphrase: str,
    title: str,
    introduction: str = "",
    body_markdown: str = "",
) -> str:
    """``description``, guaranteed to be at most ``META_DESCRIPTION_MAX_CHARS``.

    A description within the limit is returned untouched. An over-long one is
    shortened sentence-/clause-aware first (keeping the writer's wording), then
    rebuilt extractively from the article, and only as a last resort cut at a
    word boundary — so the saved value can never exceed the limit.
    """
    text = normalize_title(description)
    if len(text) <= META_DESCRIPTION_MAX_CHARS:
        return text

    shortened = shorten_meta_description(text, focus_keyphrase)
    if shortened:
        return shortened

    rebuilt = build_meta_description(
        focus_keyphrase=focus_keyphrase,
        title=title,
        introduction=introduction,
        body_markdown=body_markdown,
    )
    if rebuilt and len(rebuilt) <= META_DESCRIPTION_MAX_CHARS:
        return rebuilt

    return _trim_to_word_boundary(text, META_DESCRIPTION_MAX_CHARS)


def ensure_keyphrase_in_introduction(introduction: str, focus_keyphrase: str) -> str:
    """Prepend a keyphrase-bearing lead sentence when the intro lacks it.

    The sentence is framing, not a claim -- it names the subject and says the
    article covers it, which is true by construction.
    """
    keyphrase = normalize_title(focus_keyphrase)
    if not keyphrase:
        return introduction

    text = (introduction or "").strip()
    if contains_keyphrase(text, keyphrase):
        return introduction

    lead = (
        f"This guide walks through {keyphrase} in practical detail, "
        f"so you know what matters and what to do next."
    )
    return f"{lead}\n\n{text}".strip() if text else lead


def enforce_onpage_seo(
    final_content: dict,
    *,
    selected_title: str = "",
    focus_keyphrase: str = "",
    stage: str = "",
) -> dict:
    """Return ``final_content`` with the content-level on-page SEO invariants held.

    Non-destructive: values that already comply are returned untouched, and a
    field is only synthesized when it is missing or non-compliant. Always
    returns a new dict so callers never mutate checkpointed state in place.
    """
    if not isinstance(final_content, dict) or not final_content:
        return final_content

    updated = dict(final_content)
    keyphrase = normalize_title(focus_keyphrase)
    # NOT normalized: the selected title is compared and restored byte-for-byte.
    # Normalizing both sides let a model title that differed only in quotes,
    # casing-neutral whitespace or surrounding punctuation pass as "unchanged".
    selected_title = selected_title or ""

    # 1. The user's selected title is the final title, full stop.
    if selected_title and updated.get("title") != selected_title:
        logger.warning(
            "enforce_onpage_seo[%s]: title %r does not match the user-selected title %r "
            "-- reverting.",
            stage or "unknown",
            updated.get("title", ""),
            selected_title,
        )
        updated["title"] = selected_title

    # 2. The focus keyphrase is the user's, never the model's own guess.
    if keyphrase and normalize_title(updated.get("focus_keyphrase")) != keyphrase:
        updated["focus_keyphrase"] = keyphrase

    # 3. meta_title IS the selected title. The writer model authors its own
    #    meta_title independently, and that value -- not `title` -- is what the
    #    editor displayed and saved back as the article title, so a differing
    #    meta_title is exactly how the user's selection got replaced. Discard it.
    if selected_title:
        if updated.get("meta_title") != selected_title:
            updated["meta_title"] = selected_title
    elif not (updated.get("meta_title") or "").strip():
        updated["meta_title"] = updated.get("title") or ""

    # 4. meta_description must exist, carry the keyphrase, and fit the limit.
    meta_description = (updated.get("meta_description") or "").strip()
    if not meta_description or (keyphrase and not contains_keyphrase(meta_description, keyphrase)):
        logger.warning(
            "enforce_onpage_seo[%s]: meta_description %s -- regenerating deterministically.",
            stage or "unknown",
            "missing" if not meta_description else "is missing the focus keyphrase",
        )
        meta_description = build_meta_description(
            focus_keyphrase=keyphrase,
            title=updated.get("title") or selected_title,
            introduction=updated.get("introduction") or "",
            body_markdown=updated.get("body_markdown") or "",
        )
        updated["meta_description"] = meta_description
    if len(meta_description) > META_DESCRIPTION_MAX_CHARS:
        fitted = fit_meta_description(
            meta_description,
            focus_keyphrase=keyphrase,
            title=updated.get("title") or selected_title,
            introduction=updated.get("introduction") or "",
            body_markdown=updated.get("body_markdown") or "",
        )
        logger.warning(
            "enforce_onpage_seo[%s]: meta_description was %d characters (max %d) -- "
            "shortened to %d.",
            stage or "unknown",
            len(meta_description),
            META_DESCRIPTION_MAX_CHARS,
            len(fitted),
        )
        updated["meta_description"] = fitted

    # 5. The introduction must carry the keyphrase.
    if keyphrase:
        introduction = updated.get("introduction") or ""
        repaired_introduction = ensure_keyphrase_in_introduction(introduction, keyphrase)
        if repaired_introduction != introduction:
            logger.warning(
                "enforce_onpage_seo[%s]: introduction was missing the focus keyphrase %r "
                "-- prepending a keyphrase lead sentence.",
                stage or "unknown",
                keyphrase,
            )
            updated["introduction"] = repaired_introduction

    return updated


def merge_preserving_existing(base: dict, incoming: dict) -> dict:
    """``{**base, **incoming}`` except that ``incoming`` may not blank a value.

    A structured-output repair/humanization pass echoes back the FULL schema,
    so every optional field it chose not to write comes back as ``None`` -- a
    plain dict merge therefore silently deletes a good ``meta_description``,
    ``slug`` or ``category`` that generation had produced. Only meaningful
    values are allowed to overwrite.
    """
    merged = dict(base or {})
    for key, value in (incoming or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict, tuple, set)) and not value and merged.get(key):
            # An intentionally-emptied collection is indistinguishable from an
            # unwritten one here, so keep whatever the base already had.
            continue
        merged[key] = value
    return merged
