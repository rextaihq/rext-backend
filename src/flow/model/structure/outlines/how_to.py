from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from .common import (
    OutlineBase,
    _canonicalize_heading,
    _ensure_focus_keyphrase_in_title,
    _ensure_no_duplicate_strings,
)


class HowToStep(BaseModel):
    step_number: int = Field(ge=1, description="Sequential step number starting at 1.")
    title: str = Field(description="Action-verb step title (no filler like 'Step 1').")
    goal: str = Field(description="What the reader will accomplish in this step.")
    instructions: Annotated[
        list[str],
        Field(min_length=2, max_length=7, description="Concise, actionable instructions."),
    ]
    tips: Optional[List[str]] = Field(
        default=None, description="Optional extra tips for this step."
    )
    warnings: Optional[List[str]] = Field(
        default=None, description="Safety / data-loss / costly mistake warnings."
    )
    done_check: Optional[List[str]] = Field(
        default=None, description="How the reader can verify the step is complete."
    )


class TroubleshootingItem(BaseModel):
    problem: str = Field(description="A likely issue the reader will face.")
    fix: Annotated[
        list[str], Field(min_length=1, max_length=5, description="Specific fixes to try.")
    ]


class HowToOutlineBase(OutlineBase):
    prerequisites: Optional[List[str]] = Field(
        default=None, description="What the reader needs before starting."
    )
    tools_or_materials: Optional[List[str]] = Field(
        default=None, description="Tools/materials/software required."
    )
    steps: Annotated[list[HowToStep], Field(min_length=5, max_length=12)]
    common_mistakes: Optional[List[str]] = Field(
        default=None, description="Mistakes to avoid (practical + specific)."
    )
    troubleshooting: Optional[List[TroubleshootingItem]] = Field(
        default=None, description="Problem/fix pairs for common failures."
    )
    wrap_up: Annotated[
        list[str],
        Field(
            min_length=2,
            max_length=5,
            description="Short wrap-up bullets: what you did + what to do next.",
        ),
    ]
    faqs: Optional[List[str]] = Field(default=None, description="FAQ questions (PAA-style).")
    schema_type: Literal["HowTo", "FAQPage"] = Field(default="HowTo")


def validate_how_to_outline(outline: HowToOutlineBase) -> None:
    _ensure_focus_keyphrase_in_title(outline.title, outline.focus_keyphrase)

    step_numbers = [s.step_number for s in outline.steps]
    if step_numbers != list(range(1, len(step_numbers) + 1)):
        raise ValueError("steps[].step_number must be sequential starting at 1")

    step_titles = [s.title for s in outline.steps]
    _ensure_no_duplicate_strings(step_titles, "steps[].title")

    bad_titles = [t for t in step_titles if _canonicalize_heading(t).startswith("step ")]
    if bad_titles:
        raise ValueError("steps[].title must not start with 'Step X' — use an action verb instead")
