from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from .common import OutlineBase, _ensure_focus_keyphrase_in_title


class NavSection(BaseModel):
    heading: str = Field(description="Specific navigational section heading (H2).")
    purpose: str = Field(description="User goal this section supports.")
    key_points: Annotated[list[str], Field(min_length=2, max_length=6)]


class NavigationalOutlineBase(OutlineBase):
    primary_cta: str = Field(description="Single primary call-to-action for this page.")
    trust_signals: Annotated[list[str], Field(min_length=2, max_length=8)]
    sections: Annotated[list[NavSection], Field(min_length=3, max_length=8)]
    faqs: Optional[List[str]] = Field(default=None)
    schema_type: Literal["WebPage", "WebSite", "AboutPage", "ContactPage"] = Field(
        default="WebPage"
    )
    target_word_count: int = Field(ge=300, le=3000)


def validate_navigational_outline(outline: NavigationalOutlineBase) -> None:
    _ensure_focus_keyphrase_in_title(outline.title, outline.focus_keyphrase)
