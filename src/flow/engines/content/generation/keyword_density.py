"""Deterministic, Yoast-style focus-keyphrase density measurement.

Nothing here calls a model. Density was previously "enforced" only as prose in
the generation system prompt ("Keyphrase density: 0.5%-2.5% - never stuff") and
as an LLM-self-reported `keyphrase_density` field that nothing ever verified;
the one place a real number could have been produced (`calculate_seokar`)
accepts `focus_keyphrase` and ignores it, reporting a generic top-10 keyword
table instead. So an article could ship with the focus keyphrase appearing
once, or forty times, and no stage could tell the difference.

Two things make this work across all 34 content types without 34 rule sets:

* Occurrences are counted as WORD SEQUENCES, so an exact multi-word keyphrase
  is measured as the phrase it is. Substring matching would count "crm" inside
  "crms" and inside a URL slug, and would never correctly count "best crm
  software for startups" at all.
* The acceptable band is derived from the FINAL WORD COUNT, not from the
  content type. A 300-word pricing page and a 4,000-word pillar article cannot
  share a single percentage: 0.5% of 300 words is one and a half occurrences
  (so the percentage floor is meaningless and an absolute occurrence floor is
  what matters), while 2.5% of 4,000 words is a hundred repetitions (so the
  percentage ceiling is what matters and is far too generous). Content type
  enters only as a light per-FAMILY modifier with a safe default.
"""

from __future__ import annotations

import math
import re
from typing import Literal, Optional

from typing_extensions import TypedDict

DensityStatus = Literal["ok", "too_low", "too_high", "not_applicable"]

# -- Yoast-derived baseline --------------------------------------------------
#
# Yoast's keyphrase-density assessment treats 0.5%-3.0% as "good", flags below
# 0.5% as "keyphrase density too low", and above 3.0% as over-optimization
# (with a harsher band above 4%). Those numbers were tuned for a typical
# 1,000-2,000 word blog post, which is why the tiers below shift them by length
# rather than applying them flat.
YOAST_MIN_DENSITY = 0.5
YOAST_MAX_DENSITY = 3.0

# Yoast also wants the keyphrase to appear at least twice in any text long
# enough to carry it -- a single occurrence reads as incidental rather than as
# the subject of the page. Below this word count one well-placed occurrence is
# the natural maximum, and demanding two is itself the stuffing failure mode.
SINGLE_OCCURRENCE_MAX_WORDS = 100
ABSOLUTE_MIN_OCCURRENCES = 2


class DensityTier(TypedDict):
    """A length band and the density range that suits it."""

    max_words: Optional[int]  # inclusive upper bound; None = open-ended
    name: str
    min_density: float
    max_density: float


# Ordered shortest-first; the first tier whose `max_words` is not exceeded wins.
#
# The shape of the curve: short pages need a HIGHER relative density to signal
# their topic at all (a 250-word contact page mentioning its keyphrase twice is
# at 1.6%, which is correct, not stuffing), while long pages need a LOWER
# ceiling because a percentage that reads as natural over 800 words reads as
# mechanical repetition over 4,000.
DENSITY_TIERS: tuple[DensityTier, ...] = (
    {"max_words": 299, "name": "very_short", "min_density": 0.8, "max_density": 3.5},
    {"max_words": 899, "name": "short", "min_density": 0.7, "max_density": 3.0},
    {"max_words": 1799, "name": "medium", "min_density": 0.5, "max_density": 2.5},
    {"max_words": 3499, "name": "long", "min_density": 0.5, "max_density": 2.0},
    {"max_words": None, "name": "very_long", "min_density": 0.4, "max_density": 1.75},
)

# Longer keyphrases are far more conspicuous per repetition -- "crm" at 2% is
# invisible, "best crm software for small business teams" at 2% is unreadable.
# Keyed by the keyphrase's word count, applied as a multiplier to the tier band.
_PHRASE_LENGTH_DAMPING: dict[int, float] = {1: 1.0, 2: 1.0, 3: 0.85, 4: 0.7}
_LONG_PHRASE_DAMPING = 0.6  # 5+ words

# Hard floor so damping can never push the minimum to an unreachable-by-rounding
# value on a long article with a long keyphrase.
_MIN_DENSITY_FLOOR = 0.25

# -- content-type families ---------------------------------------------------
#
# One modifier per FAMILY, not per content type -- the thing that actually
# varies is how much natural room the format has for repeating a phrase, and
# that is a property of the family, not of (say) "coupon-page" versus
# "checkout-page". Any content type not listed resolves to the default, so new
# types need no entry here to be handled correctly.


class FamilyModifier(TypedDict):
    min_scale: float
    max_scale: float


_DEFAULT_FAMILY_MODIFIER: FamilyModifier = {"min_scale": 1.0, "max_scale": 1.0}

FAMILY_MODIFIERS: dict[str, FamilyModifier] = {
    # Long-form prose with room to repeat naturally -- the baseline.
    "informational": {"min_scale": 1.0, "max_scale": 1.0},
    # Comparison/review copy repeats PRODUCT names heavily; forcing the generic
    # keyphrase to the same rate fights the format, so the ceiling eases down.
    "commercial": {"min_scale": 1.0, "max_scale": 0.9},
    # Reference/utility pages (docs, help center, contact) are short and
    # functional. A slightly lower floor keeps them from being failed for
    # writing naturally; the occurrence floor still guarantees presence.
    "navigational": {"min_scale": 0.85, "max_scale": 0.9},
    # Conversion copy is short and benefit-led. Same reasoning, plus a tighter
    # ceiling because stuffed sales copy is the most damaging place to stuff.
    "transactional": {"min_scale": 0.9, "max_scale": 0.85},
}

CONTENT_TYPE_FAMILIES: dict[str, str] = {
    # Informational
    "blog": "informational",
    "how-to-guide": "informational",
    "explainer": "informational",
    "pillar-content": "informational",
    "checklist": "informational",
    "tutorial": "informational",
    "faq": "informational",
    "white-paper": "informational",
    "case-study": "informational",
    "glossary": "informational",
    "resource-list": "informational",
    # Commercial
    "comparison": "commercial",
    "best-tools": "commercial",
    "alternatives": "commercial",
    "in-depth-review": "commercial",
    "pros-cons": "commercial",
    "product-roundup": "commercial",
    "buying-guide": "commercial",
    # Navigational
    "brand-page": "navigational",
    "product-homepage": "navigational",
    "feature-overview": "navigational",
    "documentation": "navigational",
    "login-guide": "navigational",
    "contact-us": "navigational",
    "about-us": "navigational",
    "help-center": "navigational",
    # Transactional
    "sales-page": "transactional",
    "pricing-page": "transactional",
    "signup-page": "transactional",
    "demo-page": "transactional",
    "coupon-page": "transactional",
    "checkout-page": "transactional",
    "landing-page": "transactional",
    "service-page": "transactional",
}


def resolve_content_family(content_type: str) -> str:
    """The family a content type belongs to; "informational" for anything unknown."""
    from src.flow.model.structure.outlines import normalize_content_type

    normalized = normalize_content_type(content_type)
    return CONTENT_TYPE_FAMILIES.get(normalized, "informational")


# -- text normalization ------------------------------------------------------

_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
# Image embeds go entirely: alt text is graded separately and counting it here
# would let an article pass on alt text alone.
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# Links keep their anchor text (it is real prose the reader sees) and drop the
# URL (a keyphrase inside a slug is not a keyphrase in the copy).
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MD_SYNTAX_RE = re.compile(r"[#>*_~|]+")
_PLACEHOLDER_MARKER_RE = re.compile(r"\{\{[^}]*\}\}")

# Words are letters/digits plus intra-word apostrophes, so "don't" stays one
# token while "small-business" splits into two the way a reader reads it.
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")


def strip_markdown_noise(text: str) -> str:
    """Reduce markdown to the prose a reader actually reads.

    Code blocks, image embeds, raw URLs, HTML tags and template markers are
    removed outright; link anchor text is kept. Without this, density is
    measured against a denominator inflated by URLs and code, and a keyphrase
    sitting in a slug or an alt attribute is scored as if it were body copy.
    """
    if not text:
        return ""
    cleaned = _CODE_FENCE_RE.sub(" ", text)
    cleaned = _INLINE_CODE_RE.sub(" ", cleaned)
    cleaned = _IMAGE_RE.sub(" ", cleaned)
    cleaned = _LINK_RE.sub(r"\1", cleaned)
    cleaned = _BARE_URL_RE.sub(" ", cleaned)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = _PLACEHOLDER_MARKER_RE.sub(" ", cleaned)
    cleaned = _MD_SYNTAX_RE.sub(" ", cleaned)
    return cleaned


def strip_link_destinations(text: str) -> str:
    """Markdown without the addresses a reader never reads: images go, a link keeps its anchor
    text, a bare address goes. Everything else stays as written, symbols included, so "C#" is
    still "C#" (strip_markdown_noise takes "#" for a heading mark)."""
    if not text:
        return ""
    cleaned = _IMAGE_RE.sub(" ", text)
    cleaned = _LINK_RE.sub(r"\1", cleaned)
    return _BARE_URL_RE.sub(" ", cleaned)


def tokenize_words(text: str) -> list[str]:
    """Lowercased word tokens, markdown already stripped by the caller."""
    return [w.lower() for w in _WORD_RE.findall(text or "")]


def count_keyphrase_occurrences(text: str, keyphrase: str) -> int:
    """Exact whole-phrase occurrences, matched as a word sequence.

    Word-sequence matching is what makes multi-word keyphrases measurable:
    "project management software" is one occurrence of a three-word phrase, not
    three separate keyword hits and not a substring that also fires inside
    "project-management-software-guide" in a URL. It also prevents the classic
    false positive where "crm" matches inside "crms" or "scrm".
    """
    phrase_tokens = tokenize_words(strip_markdown_noise(keyphrase))
    if not phrase_tokens:
        return 0
    text_tokens = tokenize_words(strip_markdown_noise(text))
    span = len(phrase_tokens)
    if span > len(text_tokens):
        return 0
    return sum(
        1 for i in range(len(text_tokens) - span + 1) if text_tokens[i : i + span] == phrase_tokens
    )


def count_words(text: str) -> int:
    """Word count over reader-visible prose -- the density denominator."""
    return len(tokenize_words(strip_markdown_noise(text)))


# -- policy + report ---------------------------------------------------------


class KeywordDensityPolicy(TypedDict):
    """The acceptable band for one specific article."""

    tier: str
    family: str
    word_count: int
    keyphrase_word_count: int
    min_density: float
    max_density: float
    target_density: float
    min_occurrences: int
    max_occurrences: int


class KeywordDensityReport(TypedDict):
    """Measured density for one article, plus the verdict against its policy."""

    keyphrase: str
    status: DensityStatus
    word_count: int
    occurrences: int
    density: float  # Yoast-compatible: occurrences / words * 100
    weighted_density: float  # share of the text the phrase occupies
    policy: KeywordDensityPolicy
    # How many occurrences to add (positive) or remove (negative) to land inside
    # the band. 0 when already compliant -- this is what the repair prompt needs.
    occurrence_delta: int
    detail: str


def _resolve_tier(word_count: int) -> DensityTier:
    for tier in DENSITY_TIERS:
        if tier["max_words"] is None or word_count <= tier["max_words"]:
            return tier
    return DENSITY_TIERS[-1]


def _phrase_damping(keyphrase_word_count: int) -> float:
    return _PHRASE_LENGTH_DAMPING.get(keyphrase_word_count, _LONG_PHRASE_DAMPING)


def resolve_density_policy(
    word_count: int,
    content_type: str = "",
    keyphrase_word_count: int = 1,
) -> KeywordDensityPolicy:
    """The density band this article should satisfy.

    Length drives the band; keyphrase length damps it; content-type family
    nudges it. The occurrence bounds are derived from the band rather than
    configured separately, so the percentage and the count can never disagree.
    """
    word_count = max(0, int(word_count))
    keyphrase_word_count = max(1, int(keyphrase_word_count))
    tier = _resolve_tier(word_count)
    family = resolve_content_family(content_type)
    modifier = FAMILY_MODIFIERS.get(family, _DEFAULT_FAMILY_MODIFIER)
    damping = _phrase_damping(keyphrase_word_count)

    min_density = max(
        _MIN_DENSITY_FLOOR,
        round(tier["min_density"] * modifier["min_scale"] * damping, 3),
    )
    max_density = round(tier["max_density"] * modifier["max_scale"] * damping, 3)
    # Damping and family scaling are applied independently to both ends, so on
    # an extreme combination they could in principle cross. Keep the band sane.
    if max_density <= min_density:
        max_density = round(min_density * 2.0, 3)

    # Occurrence bounds. The floor is the stricter of "what the percentage
    # implies" and "what a page of this length needs to read as being about the
    # phrase at all" -- on short content the latter dominates, which is exactly
    # the case a pure percentage rule gets wrong.
    density_floor = math.ceil(min_density / 100 * word_count)
    absolute_floor = 1 if word_count < SINGLE_OCCURRENCE_MAX_WORDS else ABSOLUTE_MIN_OCCURRENCES
    min_occurrences = max(absolute_floor, density_floor) if word_count else 0
    max_occurrences = math.floor(max_density / 100 * word_count)
    # Never let rounding produce a ceiling below the floor on very short text.
    max_occurrences = max(max_occurrences, min_occurrences + 1) if word_count else 0

    return KeywordDensityPolicy(
        tier=tier["name"],
        family=family,
        word_count=word_count,
        keyphrase_word_count=keyphrase_word_count,
        min_density=min_density,
        max_density=max_density,
        target_density=round((min_density + max_density) / 2, 3),
        min_occurrences=min_occurrences,
        max_occurrences=max_occurrences,
    )


def _build_detail(
    keyphrase: str,
    status: DensityStatus,
    occurrences: int,
    density: float,
    policy: KeywordDensityPolicy,
    delta: int,
) -> str:
    band = (
        f"{policy['min_density']}%-{policy['max_density']}% "
        f"({policy['min_occurrences']}-{policy['max_occurrences']} occurrences "
        f"for {policy['word_count']} words, tier={policy['tier']}, family={policy['family']})"
    )
    measured = f"'{keyphrase}' appears {occurrences}x = {density}%"
    if status == "ok":
        return f"{measured}, within target band {band}."
    if status == "too_low":
        return f"{measured}, below target band {band}. Add {delta} more natural occurrence(s)."
    return f"{measured}, above target band {band}. Remove {abs(delta)} occurrence(s)."


def analyze_keyword_density(
    text: str,
    keyphrase: str,
    content_type: str = "",
    extra_text: str = "",
) -> KeywordDensityReport:
    """Measure focus-keyphrase density and grade it against a length-aware band.

    `extra_text` counts toward occurrences but NOT toward the word count -- it is
    for surfaces that carry the keyphrase without being body copy (title, meta
    description). They legitimately raise the signal without being prose the
    reader wades through, and including them in the denominator would penalize
    an article for having a keyword-bearing meta description.
    """
    keyphrase = (keyphrase or "").strip()
    body = text or ""
    word_count = count_words(body)
    phrase_tokens = tokenize_words(strip_markdown_noise(keyphrase))
    policy = resolve_density_policy(word_count, content_type, len(phrase_tokens) or 1)

    if not phrase_tokens or word_count == 0:
        return KeywordDensityReport(
            keyphrase=keyphrase,
            status="not_applicable",
            word_count=word_count,
            occurrences=0,
            density=0.0,
            weighted_density=0.0,
            policy=policy,
            occurrence_delta=0,
            detail=(
                "No focus keyphrase supplied; density not applicable."
                if not phrase_tokens
                else "No measurable content; density not applicable."
            ),
        )

    occurrences = count_keyphrase_occurrences(body, keyphrase)
    if extra_text:
        occurrences += count_keyphrase_occurrences(extra_text, keyphrase)

    density = round(occurrences / word_count * 100, 3)
    weighted_density = round(occurrences * len(phrase_tokens) / word_count * 100, 3)

    if occurrences < policy["min_occurrences"] or density < policy["min_density"]:
        status: DensityStatus = "too_low"
        needed = max(
            policy["min_occurrences"],
            math.ceil(policy["min_density"] / 100 * word_count),
        )
        delta = max(1, needed - occurrences)
    elif occurrences > policy["max_occurrences"] or density > policy["max_density"]:
        status = "too_high"
        allowed = min(
            policy["max_occurrences"],
            math.floor(policy["max_density"] / 100 * word_count),
        )
        delta = min(-1, allowed - occurrences)
    else:
        status = "ok"
        delta = 0

    return KeywordDensityReport(
        keyphrase=keyphrase,
        status=status,
        word_count=word_count,
        occurrences=occurrences,
        density=density,
        weighted_density=weighted_density,
        policy=policy,
        occurrence_delta=delta,
        detail=_build_detail(keyphrase, status, occurrences, density, policy, delta),
    )


def build_density_prompt_instruction(
    keyphrase: str,
    target_word_count: int,
    content_type: str = "",
) -> str:
    """Up-front instruction for the writer model, derived from the same policy.

    Generated from `resolve_density_policy` rather than written out as prose, so
    what the model is asked for and what the deterministic check enforces cannot
    drift apart -- that drift is what turns a tightened rule into silent extra
    repair loops.
    """
    keyphrase = (keyphrase or "").strip()
    if not keyphrase or target_word_count <= 0:
        return ""
    phrase_words = len(tokenize_words(strip_markdown_noise(keyphrase))) or 1
    policy = resolve_density_policy(target_word_count, content_type, phrase_words)
    return (
        "\nFOCUS KEYPHRASE - EXACT MATCH REQUIRED:\n"
        f'- The focus keyphrase is exactly: "{keyphrase}". Use this exact wording. '
        "Do not substitute a synonym, reorder its words, or replace it with a phrase you prefer.\n"
        f"- Use it as an exact phrase between {policy['min_occurrences']} and "
        f"{policy['max_occurrences']} times across the introduction and body "
        f"(target around {policy['target_density']}% density for a {target_word_count}-word piece).\n"
        "- Required placements: the title, the first sentence of the introduction, "
        "the meta description once, and the H2/H3 headings as described under SUBHEADINGS.\n"
        "- Spread the remaining uses evenly through the body. Never force it into a "
        "sentence where it reads awkwardly - use a natural variant there instead, and "
        "keep the exact-match uses for places where the phrase genuinely fits.\n"
    )
