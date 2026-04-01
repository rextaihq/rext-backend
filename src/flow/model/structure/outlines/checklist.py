from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from .common import (
    OutlineBase,
    _ensure_focus_keyphrase_in_title,
    _ensure_no_duplicate_strings,
)


class ChecklistItem(BaseModel):
    action: str = Field(description="Actionable checklist item (imperative verb).")
    why: str = Field(description="Why this item matters (one sentence).")
    how_to_verify: str = Field(description="How to confirm it's done correctly.")
    priority: Literal["must", "should", "nice-to-have"] = Field(default="should")


class ChecklistCategory(BaseModel):
    name: str = Field(description="Category name (specific, not generic).")
    items: Annotated[list[ChecklistItem], Field(min_length=3, max_length=12)]


class ChecklistOutlineBase(OutlineBase):
    checklist_purpose: str = Field(description="What the checklist helps the reader accomplish.")
    categories: Annotated[list[ChecklistCategory], Field(min_length=2, max_length=7)]
    how_to_use: Annotated[
        list[str],
        Field(min_length=2, max_length=6, description="Practical guidance on using the checklist."),
    ]
    quick_summary: Optional[List[str]] = Field(
        default=None, description="Optional quick reference summary bullets."
    )
    faqs: Optional[List[str]] = Field(default=None)
    schema_type: Literal["Article"] = Field(default="Article")


def validate_checklist_outline(outline: ChecklistOutlineBase) -> None:
    _ensure_focus_keyphrase_in_title(outline.title, outline.focus_keyphrase)
    category_names = [c.name for c in outline.categories]
    _ensure_no_duplicate_strings(category_names, "categories[].name")
