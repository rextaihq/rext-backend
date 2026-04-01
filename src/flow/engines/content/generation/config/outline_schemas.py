from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class BaseSection(BaseModel):
    section_type: str
    heading: str
    heading_level: Literal["H1", "H2", "H3"] = "H2"
    description: str
    key_points: List[str] = Field(default_factory=list)
    content_format: Optional[str] = None


class BaseOutline(BaseModel):
    title: str
    brief: str = ""
    sections: List[BaseSection]
    target_audience: List[str] = Field(default_factory=list)
    tone: Literal["Professional", "Conversational", "Authoritative"] = "Professional"
    keywords_to_include: List[str] = Field(default_factory=list)
    target_word_count: int = 1500


class InformationalOutline(BaseOutline):
    faqs: List[str] = Field(default_factory=list)


class ListOutline(BaseOutline):
    pass


class ComparisonOutline(BaseOutline):
    pass


class ConversionOutline(BaseOutline):
    primary_cta: str = ""
