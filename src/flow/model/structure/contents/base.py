from typing import List, Optional
from pydantic import BaseModel, Field
from src.flow.model.structure.content import CTABlock, ImageAltText, Link, SchemaMarkup
from typing import Any
from pydantic import model_validator
from src.flow.model.structure.outline import Fact


class ContentBlock(BaseModel):
    """One structural section of a generated article.

    The unit a structured body is built from. The approved outline already
    defines WHICH blocks a content type has and whether each is required
    (see engines/content/generation/outline_structure.resolve_outline_structure),
    so this model deliberately carries no schema knowledge of its own — it is
    just "a heading and its prose". That keeps the outline the single source of
    truth for structure rather than creating a second definition that can drift.
    """

    heading: Optional[str] = Field(
        default=None,
        description=(
            "The reader-facing H2 for this section, e.g. 'Why onboarding stalls'. "
            "Leave null for blocks that are not a titled section in the finished "
            "article — a hero or a final CTA is opening/closing copy, and emitting "
            "its schema field name ('Hero', 'Final CTA') as a visible heading is a "
            "defect. Never use the schema field name as the heading."
        ),
    )
    markdown: str = Field(
        description=(
            "This section's body copy as markdown. Do not repeat the heading "
            "inside it — the heading is rendered from the `heading` field."
        ),
    )


def blocks_to_body_markdown(ordered_blocks: List[tuple[str, Optional["ContentBlock"]]]) -> str:
    """Assemble ordered (key, block) pairs into the `body_markdown` string.

    `body_markdown` stays the representation every downstream consumer already
    reads — persistence, the WordPress publisher, EEAT/on-page/readability
    scoring, the API response schemas and every existing validator. Structured
    generation changes how the string is PRODUCED, not what receives it, which
    is what keeps this change backward-compatible.

    Absent optional blocks are skipped rather than rendered empty.
    """
    parts: List[str] = []
    for _key, block in ordered_blocks:
        if block is None:
            continue
        body = (block.markdown or "").strip()
        if not body:
            continue
        heading = (block.heading or "").strip()
        parts.append(f"## {heading}\n\n{body}" if heading else body)
    return "\n\n".join(parts)


class BaseGeneratedContent(BaseModel):
    """Base model for all generated content types."""
    title: str = Field(
        description=(
            "SEO page title: 20–60 characters, ≤10 words. "
            "Focus keyphrase MUST appear at the very beginning. No clickbait."
        )
    )
    slug: Optional[str] = Field(
        default=None,
        description="Lowercase SEO-friendly slug using hyphens only. ≤80 chars. No stop words.",
    )
    meta_title: Optional[str] = Field(
        default=None,
        description="SEO meta title: 50–60 chars, ≤10 words. Focus keyphrase must be present.",
    )
    meta_description: Optional[str] = Field(
        default=None,
        description=(
            "SEO meta description: 140–160 chars. "
            "Include focus keyphrase exactly once, naturally. End with a call-to-action."
        ),
    )
    tags: List[str] = Field(default_factory=list, description="List of tags.")
    category: Optional[str] = Field(
        default=None,
        description="One concise topical WordPress category name for this content.",
    )
    focus_keyphrase: Optional[str] = Field(default=None, description="Primary focus keyphrase.")
    keyphrase_density: Optional[float] = Field(
        default=None,
        description="Keyphrase density percentage. Target 0.5%–2.5%. Never stuff.",
    )
    secondary_keywords: List[str] = Field(default_factory=list, description="Secondary keywords.")
    introduction: Optional[str] = Field(
        default=None,
        description=(
            "Opening section: focus keyphrase MUST appear in the very first sentence. "
            "Write 3 to 4 paragraphs — do not write a single short paragraph. "
            "HARD CEILING: the introduction sits before the first H2, so Yoast's "
            "300-word subheading-distance rule applies to it as one unbroken block — "
            "keep the whole introduction under roughly 220 words total. Let the "
            "paragraphs vary unevenly in length rather than 4 equal-sized ones."
        ),
    )
    body_markdown: Optional[str] = Field(
        default=None,
        description=(
            "Complete body in Markdown (excluding introduction). "
            "Must meet the target word count specified in the prompt. "
            "SEO REQUIREMENTS (apply where structurally appropriate): "
            "(1) H2 headings: ≤8 words, ≤58 chars. H3 headings: ≤6 words, ≤48 chars. "
            "(2) At least one image with the focus keyphrase in its alt text. "
            "(3) At least one internal link woven naturally into the body. "
            "(4) Every H2 section must be substantial — no stub sections. "
            "Elaborate with examples, data, step-by-step breakdowns, and real-world anecdotes, "
            "but split the elaboration across H3 subsections rather than one long block. "
            "The text directly under an H2, before its first H3, must stay short "
            "(well under 150 words) — do NOT write a long lead-in paragraph before "
            "diving into H3s. Yoast flags any 300+ word stretch between headings, at "
            "any level, including that H2-to-first-H3 gap. "
            "CRITICAL: Every URL in internal_links MUST appear as an inline hyperlink "
            "[anchor text](url) woven into the most topically relevant sentence."
        ),
    )
    images: List[ImageAltText] = Field(
        default_factory=list,
        description=(
            "SEO-optimised image alt suggestions. "
            "At least one must include the focus keyphrase exactly."
        ),
    )
    internal_links: List[Link] = Field(
        default_factory=list,
        description=(
            "MANDATORY: populate this with every internal link provided in the prompt's "
            "INTERNAL LINKS block. Every URL in this list MUST also be embedded as an "
            "inline hyperlink inside body_markdown. Do not omit any link from the prompt."
        ),
    )
    outbound_links: List[Link] = Field(
        default_factory=list,
        description=(
            "Outbound links to authoritative external sources. "
            "Include at least one per major section where relevant (supports E-E-A-T)."
        ),
    )
    schema_markup: Optional[SchemaMarkup] = Field(
        default=None,
        description=(
            "JSON-LD schema markup. Match the type to the content "
            "(Article, HowTo, FAQPage, Product, etc.)."
        ),
    )
    facts: List[Fact] = Field(default_factory=list, description="Verifiable facts/statistics.")
    cta: Optional[CTABlock] = Field(
        default=None,
        description=(
            "Primary call-to-action, ONLY if the approved outline defines one for this "
            "content type (e.g. a landing/sales/signup page's hero or final CTA). Leave "
            "null for content types with no CTA in the outline — do not invent one."
        ),
    )

    @model_validator(mode='after')
    def enforce_internal_links_in_body(self) -> "BaseGeneratedContent":
        """Hard fallback: any internal link URL not found in body_markdown gets appended."""
        if not self.body_markdown or not self.internal_links:
            return self
        body = self.body_markdown
        missing = [lnk for lnk in self.internal_links if lnk.url and lnk.url not in body]
        if missing:
            appended = "\n\n" + "\n".join(
                f"[{lnk.anchor_text or lnk.url}]({lnk.url})"
                for lnk in missing
            )
            self.body_markdown = body + appended
        return self

    @model_validator(mode='before')
    @classmethod
    def fix_links_raw(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ['internal_links', 'outbound_links']:
                raw_links = data.get(field_name, [])
                
                if not isinstance(raw_links, list):
                    raw_links = []

                fixed_links = []
                
                for link_raw in raw_links:
                    if isinstance(link_raw, dict):
                        link_dict = link_raw.copy()

                        # ✅ FIX: infer link_type correctly
                        if field_name == "internal_links":
                            link_dict.setdefault('link_type', 'internal')
                        else:
                            link_dict.setdefault('link_type', 'external')

                        # ✅ FIX: required fallback fields
                        link_dict.setdefault('placement', 'body')

                        # 🚨 CRITICAL FIX
                        link_dict.setdefault(
                            'anchor_text',
                            link_dict.get('url', 'Read more')
                        )

                        fixed_links.append(link_dict)
                
                data[field_name] = fixed_links
        
        return data

if __name__=="__main__":
    pass
