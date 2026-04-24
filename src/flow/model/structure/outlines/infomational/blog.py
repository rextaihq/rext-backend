from typing import Literal
from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section, Fact  # noqa: F401


class BlogOutline(BaseOutline):
    schema_type: Literal["Article", "HowTo", "FAQPage", "BlogPosting"] = Field(
        default="Article",
        description="Primary schema.org type for structured data."
    )
    target_word_count: int = Field(
        ge=800,
        le=5000,
        description="Target word count for the complete article."
    )
