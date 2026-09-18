"""Canonical building blocks shared by the outline schemas.

Why this module exists
----------------------
The same concepts were re-declared independently in nearly every one of the 34
content-type schemas, and the copies drifted:

    FAQItem          23 declarations
    CTASection       23 declarations -> 13 mutually incompatible shapes
    FAQSection       21 declarations
    InternalLink      9 declarations ->  5 shapes
    EEATSignals       3 declarations ->  3 shapes
                                        (`trust_signals` vs `trust_elements`,
                                         `authority_signals` vs `authority_sources`)

That drift is not cosmetic. The generic renderers in `outlines/render.py` locate
prose and labels by *field name* (`_LABEL_FIELDS`, `_ANSWER_PROSE_FIELDS`), so
every synonym a copy invented — `issue` vs `problem`, `how_to_avoid` vs
`prevention`, `objection` vs `concern`, `query` vs `question` — had to be added
by hand to those tables. The tables grew to 40+ entries with per-schema comments
because the schemas below them had no shared vocabulary. Fixing the vocabulary
here is what lets those tables stop growing.

Using these models
------------------
Import the canonical block instead of redeclaring it::

    from src.flow.model.structure.outlines.common import FAQSection, CTASection

A content type that genuinely needs extra fields should SUBCLASS rather than
fork, so the shared field names survive and the renderers keep working::

    class TutorialFAQItem(FAQItem):
        difficulty_level: str

`OutlineContract` carries the guidance/structural split as a `ClassVar`, so a
schema declares its own non-section fields instead of `outline_structure.py`
maintaining a central table of them. `ClassVar` is excluded from Pydantic's
field set, so none of this reaches the JSON schema handed to the LLM.
"""

from __future__ import annotations

from typing import ClassVar, List, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Field roles
# ---------------------------------------------------------------------------

#: Fields that shape HOW the article is written but are never sections OF it —
#: SEO targets, intent models, E-E-A-T signals, link plans, reference lists.
#: `outline_structure.resolve_outline_structure` skips these when deriving the
#: article's structure, and `resolve_guidance_blocks` renders them as writing
#: guidance instead.
DEFAULT_GUIDANCE_FIELDS: frozenset[str] = frozenset(
    {
        "seo",
        "search_intent",
        "intent",
        "eeat",
        "engagement",
        "authority",
        "ux",
        "topic_cluster",
        "topic_authority",
        "semantic_coverage",
        "coverage",
        "entity_graph",
        "content_depth",
        "internal_links",
        "internal_linking",
        "references",
        "snippets",
        "media",
        "visuals",
        "effort",
        "user_journey",
        # Evidence and media plans reach the writer through their own dedicated
        # prompt blocks ("KEY FACTS TO INCLUDE IN CONTENT" / "IMAGE PLACEMENT
        # GUIDE"), so they must not also resolve as article sections.
        "key_facts",
        "facts",
        "image_suggestions",
    }
)


class OutlineContract(BaseModel):
    """Base for every content-type outline schema.

    Subclasses may narrow or extend the guidance set without any edit to
    `outline_structure.py` — the resolver asks the model, and only falls back to
    the module default for schemas that have not been migrated yet.
    """

    GUIDANCE_FIELDS: ClassVar[frozenset[str]] = DEFAULT_GUIDANCE_FIELDS


# ---------------------------------------------------------------------------
# Search intent / topical authority
# ---------------------------------------------------------------------------


class SearchIntent(BaseModel):
    """Why the searcher issued the query, in the standard SERP taxonomy."""

    intent_type: Literal[
        "informational",
        "commercial",
        "navigational",
        "transactional",
    ] = Field(
        default="informational",
        description=(
            "Standard SERP intent taxonomy — kept aligned with "
            "`base.Section.search_intent` and the router's intent values."
        ),
    )
    intent_modifier: Optional[
        Literal[
            "educational",
            "problem_solving",
            "comparison",
            "definition",
        ]
    ] = Field(
        default=None,
        description="Finer-grained shading of the intent, when useful.",
    )
    user_goal: List[str] = Field(
        default_factory=list,
        description="What the reader is trying to accomplish.",
    )
    expected_outcome: str = Field(description="What the reader should be able to do after reading.")


class TopicCluster(BaseModel):
    """Where this article sits in the site's topical map."""

    pillar_topic: Optional[str] = Field(
        default=None,
        description="Parent pillar page this article supports, if any.",
    )
    supporting_topics: List[str] = Field(default_factory=list)
    semantic_keywords: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# E-E-A-T
# ---------------------------------------------------------------------------


class EEATSignals(BaseModel):
    """Experience, Expertise, Authoritativeness, Trust.

    Canonical field names are the `*_signals` quartet. The `authority_sources` /
    `expertise_indicators` / `trust_elements` variants that appeared in forked
    copies are synonyms — subclass and alias if a schema truly needs them.
    """

    experience_signals: List[str] = Field(
        default_factory=list,
        description="First-hand use, testing, or lived experience to demonstrate.",
    )
    expertise_signals: List[str] = Field(
        default_factory=list,
        description="Depth, credentials, or technical precision to demonstrate.",
    )
    authority_signals: List[str] = Field(
        default_factory=list,
        description="Recognition, citations, or industry standing to reference.",
    )
    trust_signals: List[str] = Field(
        default_factory=list,
        description="Transparency, limitations, sourcing, and disclosure to include.",
    )


# ---------------------------------------------------------------------------
# FAQ
# ---------------------------------------------------------------------------


class FAQItem(BaseModel):
    """One question/answer pair. Feeds FAQPage JSON-LD."""

    question: str = Field(description="The question, phrased as a real search query.")
    answer: str = Field(description="A direct, self-contained answer.")


class FAQSection(BaseModel):
    faqs: List[FAQItem] = Field(
        default_factory=list,
        description="Real PAA-derived questions with direct answers.",
    )


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------


class InternalLink(BaseModel):
    anchor_text: str = Field(description="Natural anchor text — never 'internal link'.")
    target_page: str = Field(description="The page or topic this should point to.")
    purpose: Optional[str] = Field(
        default=None,
        description="Why this link helps the reader.",
    )


class InternalLinking(BaseModel):
    links: List[InternalLink] = Field(default_factory=list)


class ExternalReference(BaseModel):
    source_name: str = Field(description="Publication or organisation name.")
    url: Optional[str] = Field(
        default=None,
        description="Exact URL from a search result. Never invent one.",
    )
    reason: str = Field(description="What claim this source supports.")


class References(BaseModel):
    sources: List[ExternalReference] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engagement
# ---------------------------------------------------------------------------


class EngagementElement(BaseModel):
    type: Literal["example", "analogy", "case_study", "story", "statistic"]
    content: str = Field(description="The concrete example, analogy, or data point.")


class EngagementPlan(BaseModel):
    elements: List[EngagementElement] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SEO
# ---------------------------------------------------------------------------


class SEOPlan(BaseModel):
    """Keyphrase strategy.

    `focus_keyphrase` / `keywords_to_include` live at the TOP LEVEL of the
    outline — every downstream reader looks for them there — so they are
    deliberately not duplicated inside this block.
    """

    secondary_keywords: List[str] = Field(default_factory=list)
    search_variants: List[str] = Field(
        default_factory=list,
        description="Query variants and paraphrases to cover for semantic breadth.",
    )
    title_variations: Optional[List[str]] = Field(default=None)
    meta_description: Optional[str] = Field(
        default=None,
        max_length=170,
        description=(
            "Proposed meta description, 120-140 characters (hard maximum 140), containing "
            "the focus keyphrase."
        ),
    )


# ---------------------------------------------------------------------------
# CTA
# ---------------------------------------------------------------------------


class CTASection(BaseModel):
    """Call to action.

    IMPORTANT: `requirements_spec.resolve_outline_cta` treats a populated
    `primary_cta` as "this article MUST contain a CTA", and validation then
    blocks on it. Conversion-oriented content types (sales, pricing, signup,
    landing, ...) legitimately want that, and should declare their `cta` field
    as required. Informational types should not — they should declare
    `Optional[CTASection] = None` so an educational article is never forced into
    a conversion ask.

    Note the Pydantic v2 rule this class exists to get right: `Optional[str]`
    with no default is a REQUIRED nullable field, not an optional one. Every
    field here carries an explicit default.
    """

    primary_cta: Optional[str] = Field(default=None)
    secondary_cta: Optional[str] = Field(default=None)
    informational_cta: Optional[str] = Field(
        default=None,
        description="Soft next-read prompt, e.g. 'Explore related guides'.",
    )


__all__ = [
    "DEFAULT_GUIDANCE_FIELDS",
    "OutlineContract",
    "SearchIntent",
    "TopicCluster",
    "EEATSignals",
    "FAQItem",
    "FAQSection",
    "InternalLink",
    "InternalLinking",
    "ExternalReference",
    "References",
    "EngagementElement",
    "EngagementPlan",
    "SEOPlan",
    "CTASection",
]
