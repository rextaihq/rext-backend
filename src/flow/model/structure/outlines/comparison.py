from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from .common import (
    OutlineBase,
    _ensure_focus_keyphrase_in_title,
    _ensure_no_duplicate_strings,
)


class ComparedEntity(BaseModel):
    name: str = Field(description="Exact product/service/entity name.")
    best_for: str = Field(description="Best-fit use case/persona (one sentence).")
    key_strengths: Annotated[list[str], Field(min_length=2, max_length=6)]
    key_limitations: Annotated[list[str], Field(min_length=1, max_length=5)]


class ComparisonCriterion(BaseModel):
    criterion: str = Field(description="Comparison criterion (e.g., Pricing, Ease of Use).")
    why_it_matters: str = Field(description="Why this criterion matters to the decision.")
    how_to_judge: str = Field(description="How the reader should evaluate this criterion.")


class EntityNote(BaseModel):
    entity_name: str
    note: str = Field(description="Short side-by-side note for this criterion.")


class ComparisonTableRow(BaseModel):
    criterion: str
    entity_notes: Annotated[list[EntityNote], Field(min_length=2)]


class Recommendation(BaseModel):
    scenario: str = Field(description="Decision scenario (e.g., 'best for startups under $50/mo').")
    pick: str = Field(description="The recommended entity name.")
    reasoning: Annotated[list[str], Field(min_length=2, max_length=5)]


class ComparisonOutlineBase(OutlineBase):
    compared_entities: Annotated[list[ComparedEntity], Field(min_length=2, max_length=6)]
    evaluation_criteria: Annotated[list[ComparisonCriterion], Field(min_length=3, max_length=8)]
    comparison_table: Optional[List[ComparisonTableRow]] = Field(
        default=None,
        description="Optional structured comparison table rows (criterion -> notes per entity).",
    )
    decision_guide: Annotated[
        list[str],
        Field(
            min_length=3,
            max_length=7,
            description="Reader guidance on how to choose (priorities, tradeoffs, budget).",
        ),
    ]
    recommendations: Annotated[list[Recommendation], Field(min_length=2, max_length=5)]
    verdict: str = Field(description="Clear final recommendation (winner or best per scenario).")
    faqs: Optional[List[str]] = Field(
        default=None, description="FAQ questions addressing buyer doubts."
    )
    schema_type: Literal["Article", "ItemList"] = Field(default="Article")


def validate_comparison_outline(outline: ComparisonOutlineBase) -> None:
    _ensure_focus_keyphrase_in_title(outline.title, outline.focus_keyphrase)

    entity_names = [e.name for e in outline.compared_entities]
    _ensure_no_duplicate_strings(entity_names, "compared_entities[].name")

    criteria = [c.criterion for c in outline.evaluation_criteria]
    _ensure_no_duplicate_strings(criteria, "evaluation_criteria[].criterion")

    picks = {r.pick for r in outline.recommendations}
    unknown = sorted(p for p in picks if p not in set(entity_names))
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(
            "recommendations[].pick must be one of compared_entities[].name "
            f"(unknown: {joined})"
        )
