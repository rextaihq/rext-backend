"""Relevance scoring between an author persona and the article being planned.

The persona a brand should write *as* is not a property of the brand — it is a
property of the article. A site with an SEO strategist, an AI researcher and a
web designer on staff has no single "best" author; it has a best author for
this topic, this title, this search intent and this content type. So the score
is computed at outline time, against the outline, and never during persona
extraction, where none of those four things exist yet.

Scoring is deterministic (lexical overlap, no model call) for three reasons:
the outline node already spends its LLM budget on the outline itself, a score
the user sees next to a recommendation should not change between two runs of
the same outline, and a deterministic score is testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

# Words that carry no topical signal. Kept deliberately small: a stop list long
# enough to strip domain nouns would strip the very tokens the score is built on.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "best",
        "by",
        "complete",
        "for",
        "from",
        "guide",
        "how",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "the",
        "their",
        "to",
        "top",
        "ultimate",
        "up",
        "vs",
        "what",
        "when",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    }
)

# What each search intent actually sounds like in a person's title or bio.
# An intent name ("informational") never appears in a persona profile, so the
# raw word on its own would score every persona at zero and make the dimension
# dead weight.
_INTENT_VOCABULARY: dict[str, frozenset[str]] = {
    "informational": frozenset(
        {
            "informational",
            "education",
            "educator",
            "teacher",
            "trainer",
            "research",
            "researcher",
            "analyst",
            "scientist",
            "engineer",
            "writer",
            "editor",
            "explainer",
            "tutorial",
            "academic",
        }
    ),
    "commercial": frozenset(
        {
            "commercial",
            "buying",
            "comparison",
            "review",
            "reviewer",
            "product",
            "pricing",
            "vendor",
            "marketing",
            "marketer",
            "consultant",
            "strategist",
            "growth",
            "advisor",
        }
    ),
    "transactional": frozenset(
        {
            "transactional",
            "purchase",
            "checkout",
            "conversion",
            "sales",
            "revenue",
            "ecommerce",
            "merchant",
            "pricing",
            "growth",
        }
    ),
    "navigational": frozenset(
        {
            "navigational",
            "brand",
            "community",
            "support",
            "success",
            "documentation",
            "advocate",
            "evangelist",
        }
    ),
}

# Content-type families, by the words a person who writes them would use about
# themselves. Types absent here fall back to their own name split on "_", which
# is usually already descriptive ("buying_guide" -> {"buying"}).
_CONTENT_TYPE_VOCABULARY: dict[str, frozenset[str]] = {
    "blog": frozenset({"blog", "blogger", "article", "writer", "content"}),
    "how_to": frozenset({"tutorial", "step", "practitioner", "trainer", "teacher", "hands"}),
    "listicle": frozenset({"roundup", "curator", "editor", "list"}),
    "comparison": frozenset(
        {"comparison", "compare", "versus", "evaluation", "reviewer", "analyst"}
    ),
    "buying_guide": frozenset(
        {"buying", "purchase", "product", "reviewer", "advisor", "consultant"}
    ),
    "product_roundup": frozenset({"roundup", "product", "reviewer", "curator"}),
    "in_depth_review": frozenset({"review", "reviewer", "tester", "analyst", "critic"}),
    "pros_cons": frozenset({"review", "reviewer", "analyst", "evaluation"}),
    "alternatives": frozenset({"alternatives", "comparison", "reviewer", "analyst"}),
    "case_study": frozenset({"case", "study", "results", "analysis", "consultant", "practitioner"}),
    "white_paper": frozenset(
        {"paper", "research", "analysis", "technical", "scientist", "engineer"}
    ),
    "resource_list": frozenset({"resource", "curator", "librarian", "editor"}),
    "brand_page": frozenset({"brand", "founder", "marketing", "communications"}),
    "faq": frozenset({"support", "success", "educator", "documentation"}),
    "glossary": frozenset({"glossary", "educator", "editor", "documentation"}),
}

# Topic and title describe the article directly; intent and content type
# describe the shape it takes. Both matter, the first pair more.
_WEIGHTS = {
    "topic": 0.35,
    "title": 0.25,
    "search_intent": 0.20,
    "content_type": 0.20,
}

# A persona whose stated area of expertise is written out in full in the topic
# or title ("SEO" in "Technical SEO for Shopify") is a match no token ratio
# should be allowed to dilute below this.
_PHRASE_MATCH_FLOOR = 85.0

# How much of the article's subject a persona's stated expertise must cover before
# the article may present them as someone with experience in it: an author bio,
# "I'm <name>, a <title>", credentials (G56, rext-control #501). Measured as
# `subject_fit`, the better of the topic and title against the persona's title
# and areas of expertise only. The description and bio stay out: their generic
# words ("practical ideas") are no expertise in bakeries, and neither intent nor
# content type speaks to the subject. 30 is about a third of the subject's
# meaningful words ("Marketing Consultant, email campaigns" scores 40 on "email
# marketing ideas for local bakeries"); any speciality named whole in the topic
# or title clears it at 85.
TOPIC_FIT_THRESHOLD = 30.0


@dataclass
class PersonaRelevance:
    """One persona's fit for the article being outlined."""

    persona_id: str
    name: str
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)

    # The stated expertise against the article's subject (subject_fit), 0-100.
    subject_fit: float = 0.0

    @property
    def fits_topic(self) -> bool:
        """Whether the article may speak from this persona's experience."""
        return self.subject_fit >= TOPIC_FIT_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "score": self.score,
            "breakdown": dict(self.breakdown),
            "fits_topic": self.fits_topic,
        }


def _tokens(text: Any) -> set[str]:
    """Meaningful lowercase word tokens, stop words and 1-character noise removed."""
    if text is None:
        return set()
    if isinstance(text, (list, tuple, set)):
        text = " ".join(str(item) for item in text if item)
    elif isinstance(text, dict):
        text = " ".join(str(value) for value in text.values() if value)
    words = re.findall(r"[a-z0-9]+", str(text).lower())
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS}


def _expertise_phrases(persona: Any) -> list[str]:
    """The persona's stated specialities, as whole phrases ("link building")."""
    raw = _attr(persona, "areas_of_expertise")
    if isinstance(raw, str):
        items: Iterable[Any] = raw.split(",")
    elif isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = []
    phrases = []
    for item in items:
        phrase = re.sub(r"\s+", " ", str(item or "")).strip().lower()
        if len(phrase) > 1:
            phrases.append(phrase)
    title = str(_attr(persona, "professional_title") or "").strip().lower()
    if title:
        phrases.append(title)
    return phrases


def _attr(persona: Any, name: str) -> Any:
    """Read a field off either a Persona row or a plain dict."""
    if isinstance(persona, dict):
        return persona.get(name)
    return getattr(persona, name, None)


def _persona_tokens(persona: Any) -> set[str]:
    """Everything the persona claims to be, as tokens.

    The person's *name* is deliberately excluded: a persona called "Mark Webb"
    must not score on an article about web design.
    """
    tokens: set[str] = set()
    for fieldname in ("professional_title", "areas_of_expertise", "description", "bio"):
        tokens |= _tokens(_attr(persona, fieldname))
    return tokens


def _expertise_tokens(persona: Any) -> set[str]:
    """What the persona states as expertise: its title and areas, not its narrative."""
    tokens: set[str] = set()
    for fieldname in ("professional_title", "areas_of_expertise"):
        tokens |= _tokens(_attr(persona, fieldname))
    return tokens


def subject_fit(persona: Any, *, topic: Optional[str] = None, title: Optional[str] = None) -> float:
    """The persona's stated expertise against the article's subject: the better of topic and title."""
    tokens = _expertise_tokens(persona)
    return max(_text_dimension(persona, tokens, topic), _text_dimension(persona, tokens, title))


def _coverage(persona_tokens: set[str], context_tokens: set[str]) -> float:
    """Share of the article's vocabulary the persona speaks, 0-100."""
    if not persona_tokens or not context_tokens:
        return 0.0
    return round(100.0 * len(persona_tokens & context_tokens) / len(context_tokens), 2)


def _text_dimension(persona: Any, persona_tokens: set[str], text: Optional[str]) -> float:
    """Score one free-text dimension (topic or title)."""
    if not text:
        return 0.0
    score = _coverage(persona_tokens, _tokens(text))
    lowered = str(text).lower()
    for phrase in _expertise_phrases(persona):
        if phrase and _names_phrase(lowered, phrase):
            score = max(score, _PHRASE_MATCH_FLOOR)
            break
    return round(score, 2)


def _names_phrase(text: str, phrase: str) -> bool:
    """Whether the text names the phrase as whole words: "AI" is not in "email", "SEO" is in
    "technical seo audits"."""
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _vocabulary_dimension(persona_tokens: set[str], vocabulary: set[str]) -> float:
    """Score a dimension whose meaning lives in a vocabulary, not in its name.

    Measured as the share of the persona's matching vocabulary rather than of
    the whole vocabulary: a persona is not a worse fit for "informational"
    because that word has fourteen synonyms and they only use two of them.
    """
    if not persona_tokens or not vocabulary:
        return 0.0
    hits = len(persona_tokens & vocabulary)
    if not hits:
        return 0.0
    # 1 hit -> 60, 2 -> 80, 3 or more -> 100. Any hit is real evidence; more
    # hits should still rank above fewer.
    return round(min(100.0, 40.0 + (20.0 * hits)), 2)


def _intent_vocabulary(search_intent: Optional[str]) -> set[str]:
    key = str(search_intent or "").strip().lower()
    vocabulary = set(_tokens(key))
    for name, words in _INTENT_VOCABULARY.items():
        if name in key:
            vocabulary |= set(words)
    return vocabulary


def _content_type_vocabulary(content_type: Optional[str]) -> set[str]:
    key = str(content_type or "").strip().lower()
    vocabulary = set(_tokens(key.replace("_", " ")))
    vocabulary |= set(_CONTENT_TYPE_VOCABULARY.get(key, frozenset()))
    return vocabulary


def score_persona(
    persona: Any,
    *,
    topic: Optional[str] = None,
    title: Optional[str] = None,
    search_intent: Optional[str] = None,
    content_type: Optional[str] = None,
) -> PersonaRelevance:
    """Score one persona against the four things that define this article."""
    persona_tokens = _persona_tokens(persona)

    breakdown = {
        "topic": _text_dimension(persona, persona_tokens, topic),
        "title": _text_dimension(persona, persona_tokens, title),
        "search_intent": _vocabulary_dimension(persona_tokens, _intent_vocabulary(search_intent)),
        "content_type": _vocabulary_dimension(
            persona_tokens, _content_type_vocabulary(content_type)
        ),
    }
    score = round(sum(breakdown[name] * weight for name, weight in _WEIGHTS.items()), 2)

    return PersonaRelevance(
        persona_id=str(_attr(persona, "id") or ""),
        name=str(_attr(persona, "full_name") or _attr(persona, "name") or ""),
        score=score,
        breakdown=breakdown,
        subject_fit=subject_fit(persona, topic=topic, title=title),
    )


def rank_personas(
    personas: Iterable[Any],
    *,
    topic: Optional[str] = None,
    title: Optional[str] = None,
    search_intent: Optional[str] = None,
    content_type: Optional[str] = None,
) -> list[PersonaRelevance]:
    """Score every persona, best fit first.

    Ties keep the order they were given in, so a caller that passes personas
    newest-first gets the newest of two equally-fitting personas.
    """
    scored = [
        score_persona(
            persona,
            topic=topic,
            title=title,
            search_intent=search_intent,
            content_type=content_type,
        )
        for persona in personas
    ]
    return sorted(scored, key=lambda relevance: relevance.score, reverse=True)


def recommend_persona(ranked: Iterable[PersonaRelevance]) -> Optional[str]:
    """The persona an article defaults to: the best-ranked one whose stated expertise fits the subject.

    None when no persona fits (E26, rext-control#559): an article on a subject the workspace's
    people don't speak to is written by no persona unless the user picks one, rather than by
    whichever of them ranked first.
    """
    return next((relevance.persona_id for relevance in ranked if relevance.fits_topic), None)


def persona_fits_topic(
    persona: Any, *, topic: Optional[str] = None, title: Optional[str] = None
) -> bool:
    """Whether an article on this topic and title may speak from the persona's experience."""
    return subject_fit(persona, topic=topic, title=title) >= TOPIC_FIT_THRESHOLD
