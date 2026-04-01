from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from .common import (
    OutlineBase,
    _ensure_focus_keyphrase_in_title,
    _ensure_no_duplicate_strings,
    _ensure_no_generic_headings,
)


class IntroBlock(BaseModel):
    hook: str = Field(description="1-2 sentence hook that matches the intent and keyword.")
    context: str = Field(description="What problem / situation the reader is in.")
    promise: str = Field(description="What the reader will achieve/learn by the end.")


class ArticleH3(BaseModel):
    heading: str = Field(description="Specific H3 supporting heading.")
    purpose: str = Field(description="Why this sub-section exists.")
    key_points: Annotated[list[str], Field(min_length=2, max_length=5)]


class ArticleH2(BaseModel):
    heading: str = Field(description="Specific, keyword-rich H2 heading.")
    purpose: str = Field(description="What this section must accomplish for the reader.")
    key_points: Annotated[list[str], Field(min_length=2, max_length=5)]
    subsections: Optional[List[ArticleH3]] = Field(
        default=None,
        description="Optional H3 subsections (use sparingly).",
    )
    snippet_opportunity: bool = Field(
        default=False,
        description=(
            "True if this H2 is designed to win a featured snippet (definition/list/steps)."
        ),
    )
    suggested_word_count: int = Field(default=250, ge=120, le=700)


class ConclusionBlock(BaseModel):
    recap_points: Annotated[
        list[str],
        Field(
            min_length=2,
            max_length=5,
            description="2-5 bullets that recap the main value.",
        ),
    ]
    next_steps: Optional[List[str]] = Field(
        default=None, description="Actionable next steps / what to do after reading."
    )
    cta: str = Field(description="One clear CTA (subscribe, try tool, download, etc.).")


class ArticleOutlineBase(OutlineBase):
    intro: IntroBlock
    sections: Annotated[list[ArticleH2], Field(min_length=4, max_length=8)]
    conclusion: ConclusionBlock
    faqs: Optional[List[str]] = Field(
        default=None,
        description="FAQ questions (PAA-style) to include at the end if relevant.",
    )
    schema_type: Literal["Article", "BlogPosting"] = Field(default="Article")
    table_of_contents: bool = Field(
        default=False,
        description="Include a table of contents (recommended for pillar/long-form).",
    )


def validate_article_outline(outline: ArticleOutlineBase) -> None:
    _ensure_focus_keyphrase_in_title(outline.title, outline.focus_keyphrase)
    h2_headings = [s.heading for s in outline.sections]
    _ensure_no_duplicate_strings(h2_headings, "sections[].heading")
    _ensure_no_generic_headings(h2_headings, "sections[].heading")
