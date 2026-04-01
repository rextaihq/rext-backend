from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from .common import OutlineBase, _ensure_focus_keyphrase_in_title


class TxSection(BaseModel):
    heading: str = Field(description="Benefit-driven conversion section heading (H2).")
    goal: str = Field(description="How this section moves the reader toward conversion.")
    key_points: Annotated[list[str], Field(min_length=2, max_length=7)]


class TransactionalOutlineBase(OutlineBase):
    primary_cta: str = Field(description="Single primary CTA (e.g., 'Start Free Trial').")
    objections_addressed: Annotated[list[str], Field(min_length=3, max_length=8)]
    trust_signals: Annotated[list[str], Field(min_length=2, max_length=10)]
    risk_reversal: str = Field(description="Guarantee / refund / risk reversal statement.")
    urgency_element: Optional[str] = Field(
        default=None, description="Genuine urgency element if applicable."
    )
    sections: Annotated[list[TxSection], Field(min_length=3, max_length=8)]
    faqs: Optional[List[str]] = Field(
        default=None, description="FAQ questions tackling objections."
    )
    schema_type: Literal["WebPage", "Product", "Service", "Offer"] = Field(default="WebPage")
    target_word_count: int = Field(ge=400, le=4000)


def validate_transactional_outline(outline: TransactionalOutlineBase) -> None:
    _ensure_focus_keyphrase_in_title(outline.title, outline.focus_keyphrase)
