"""Blog outline schema (informational).

Contract notes
--------------
This schema IS the generation contract for a blog article. Three consumers read
it, and they must all keep working:

* ``engines/content/generation/outline_structure.resolve_outline_structure``
  reads the *Pydantic model* to decide which fields are structural blocks and in
  what order. Fields named in ``GUIDANCE_FIELDS`` are not sections of the
  article — they are writing guidance, and reach the writer through
  ``resolve_guidance_blocks`` instead.
* ``engines/content/generation/content_generation`` reads flat keys off the
  outline dict: ``brief``, ``keywords_to_include``, ``target_word_count``,
  ``internal_links``. Dropping one of those fields does not raise — it silently
  disables a feature.

Evidence and images are deliberately NOT planned here. The outline model runs
without tools, so it cannot source a URL; the content agent owns facts, and the
image pipeline builds its own input. See the notes on ``BlogOutline``.
* ``engines/content/generation/requirements_spec`` derives what validation
  enforces, including the CTA requirement (see ``common.CTASection``).

Shared blocks (FAQ, CTA, E-E-A-T, linking, references, SEO, intent) come from
``outlines/common`` rather than being redeclared here. Redeclaring them is how
23 forked copies of ``CTASection`` drifted into 13 incompatible shapes and
forced ``render.py`` to hand-maintain a synonym table.

``Section`` is intentionally NOT defined in this module: ``structure/outline.py``
re-exports ``Section``, so a local class of that name would shadow the canonical
``base.Section`` for every importer. The per-section model is ``BlogSection``.
"""

from typing import ClassVar, List, Literal, Optional

from pydantic import BaseModel, Field, conlist, model_validator

from src.flow.model.structure.outlines.common import (
    CTASection,
    EEATSignals,
    EngagementPlan,
    FAQItem,
    FAQSection,
    InternalLinking,
    OutlineContract,
    References,
    SearchIntent,
    SEOPlan,
    TopicCluster,
)

__all__ = [
    "BlogHero",
    "BlogSection",
    "ContentStructure",
    "BlogFAQSection",
    "BlogOutline",
]


# -------------------------
# HERO / CONTENT POSITIONING
# -------------------------


class BlogHero(BaseModel):
    headline: str = Field(
        description=(
            "The article's H1. MUST match the approved title — the pipeline pins "
            "`outline.title` to the user-selected topic, so a different headline "
            "here creates a second, competing H1."
        )
    )
    subheadline: str = Field(description="Clarifies value + intent satisfaction.")

    hook: Optional[str] = Field(default=None, description="Attention-grabbing opening angle.")


# -------------------------
# CONTENT STRUCTURE (HIERARCHICAL SECTIONS)
# -------------------------


class BlogSection(BaseModel):
    """One body section.

    Field names match ``base.Section`` so the shared renderers
    (``render._ANSWER_PROSE_FIELDS``, ``_format_outline_for_generation``) pick
    them up without per-schema special-casing.
    """

    heading: str = Field(description="Section heading text.")
    heading_level: Literal["H2", "H3"] = Field(
        description=(
            "H2 for a main section, H3 for a subsection of the H2 above it. "
            "H4 is not supported — the body assembler renders one level."
        )
    )
    description: str = Field(description="What this section will cover.")
    key_points: conlist(str, min_length=2, max_length=6)

    # NOTE: there is deliberately no `questions_to_answer` here. PAA questions
    # are owned entirely by the FAQ block (`BlogFAQSection`). Carrying them in
    # both places handed the writer the same question twice — once in the
    # section plan, once in the approved-FAQ block — with no rule about which
    # should answer it.
    snippet_target: bool = Field(
        default=False,
        description=(
            "True when this section is written to win a featured snippet or an "
            "AI-Overview citation: a direct 40-60 word answer directly under the "
            "heading, before any elaboration. At least one section should set this."
        ),
    )
    include_keyphrase_in_heading: bool = Field(
        default=False,
        description="Whether this heading should carry the focus keyphrase or a variant.",
    )
    suggested_word_count: int = Field(
        default=200,
        ge=80,
        le=800,
        description=(
            "Per-section word budget, used ONLY to size the article: "
            "`generate_outline` sums these into `target_word_count`, which is the "
            "number the reviewer approves and generation enforces. It is "
            "suppressed from the writer prompt (see "
            "`outline_structure._PROMPT_SUPPRESSED_FIELDS`) — the writer is held "
            "to the approved total, not to a per-section quota."
        ),
    )

    # NOTE: there is deliberately no per-section `facts` list. See the
    # `key_facts` note on BlogOutline — the outline model has no search tool, so
    # any `source_url` it produced here was invented.


class ContentStructure(BaseModel):
    # H2s and their H3s share one list, so the cap leaves room for subsections: 8 entries
    # in all used to mean a blog with H3s had to drop H2s for them, and anything over the
    # cap fails the whole outline at validation (rext-control#603).
    sections: conlist(BlogSection, min_length=4, max_length=16) = Field(
        description=(
            "4-8 H2 sections covering the topic end to end, including a closing "
            "summary/takeaways section, each followed by its H3 subsections where "
            "it has distinct parts: at most 16 entries in all. An H3 comes "
            "directly after its H2 or a sibling H3."
        )
    )

    @model_validator(mode="after")
    def _at_most_eight_h2s(self):
        # The 16 entries leave room for H3s, not for more main sections: past 8 H2s an outline
        # is refused, as it was when 8 entries were the cap.
        h2s = sum(1 for section in self.sections if section.heading_level == "H2")
        if h2s > 8:
            raise ValueError(f"at most 8 H2 sections, got {h2s}")
        return self


class BlogFAQSection(FAQSection):
    """Blog FAQs are mandatory and bounded — the outline prompt asks for 6-8
    PAA-derived questions, and they feed the FAQPage JSON-LD block."""

    faqs: conlist(FAQItem, min_length=4, max_length=10) = Field(
        description="Real PAA-derived questions with direct answers. Feeds FAQPage JSON-LD."
    )


# -------------------------
# FINAL BLOG OUTLINE SCHEMA
# -------------------------


class BlogOutline(OutlineContract):
    # `internal_links` is overwritten post-generation with a flat list of
    # published workspace URLs, so it is guidance, never a section. The rest
    # come from the shared default set.
    GUIDANCE_FIELDS: ClassVar[frozenset[str]] = OutlineContract.GUIDANCE_FIELDS

    # Core metadata
    title: str = Field(
        description="SEO-optimized H1. Pinned to the selected topic by the pipeline."
    )
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    brief: str = Field(description="Article goal and value proposition.")

    target_audience: List[str]
    tone: Literal[
        "Informative",
        "Educational",
        "Professional",
        "Conversational",
        "Authoritative",
        "Friendly",
        "Encouraging",
        "Neutral",
        "Analytical",
        "Trustworthy",
    ]

    focus_keyphrase: str = Field(description="Primary focus keyphrase (2-4 words).")
    keywords_to_include: conlist(str, min_length=1) = Field(
        description="Secondary and long-tail keywords to incorporate naturally."
    )

    # Core SEO + intent system
    seo: SEOPlan
    search_intent: SearchIntent

    # Content foundation
    hero: BlogHero
    topic_cluster: TopicCluster

    # Structure (core content engine)
    structure: ContentStructure

    # Authority building
    eeat: EEATSignals

    # Engagement system
    engagement: EngagementPlan

    # FAQ system
    faqs: BlogFAQSection

    # NOTE: no `key_facts` and no `image_suggestions`, by decision.
    #
    # key_facts: `generate_outline` runs the model under
    # `with_structured_output(...)` with NO tools bound, so it cannot search.
    # `Fact.source_url` requires "an exact URL returned by search_tool, never
    # invented" — a requirement the outline stage structurally cannot meet, so
    # every source_url it produced was fabricated. Evidence is owned by the
    # content agent, which does have live Tavily search and is already warned
    # about when it returns zero sourced facts (content_generation.py).
    #
    # image_suggestions: the image pipeline builds its own ArticleImageInput
    # from title/summary/keywords/audience (image_generation/pipeline.py) and
    # never read this field. It only shaped alt text, which the writer derives
    # from the section it sits in anyway.

    # Populated after generation from the workspace's published content —
    # `generate_outline` overwrites whatever is here.
    internal_links: Optional[InternalLinking] = Field(
        default=None,
        description="Leave null. Filled automatically from published workspace content.",
    )

    # External references
    references: References

    # CTA system — optional by design. An informational article must never be
    # forced into a conversion ask; see common.CTASection.
    cta: Optional[CTASection] = Field(default=None)

    # Schema — set programmatically from content_type, not by the LLM.
    # The schema.org @type is resolved separately by outlines/schema_org.py.
    schema_type: str = Field(default="Blog", description="Content type display name.")

    # Optimization layer
    content_goal: Literal[
        "educate_user",
        "rank_on_search",
        "build_authority",
        "answer_query_completely",
    ]

    target_reading_time_minutes: Optional[int] = Field(
        default=6,
        ge=2,
        le=25,
        description="Reading depth at ~225 wpm; should track target_word_count.",
    )

    target_word_count: int = Field(
        default=1200,
        ge=800,
        le=5000,
        description=(
            "Total article depth. Recomputed by `generate_outline` as the sum of "
            "`structure.sections[*].suggested_word_count`."
        ),
    )
