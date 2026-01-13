from typing import List, Optional, Literal
from pydantic import BaseModel, Field, conlist

class Section(BaseModel):
    heading: str = Field(description="Section heading text.")
    heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
    description: str = Field(description="What this section will cover.")
    key_points: conlist(str, min_length=2, max_length=4)
    questions_to_answer: Optional[List[str]] = Field(
        description="PAA or user questions to answer in this section."
    )
    snippet_target: Optional[bool] = False
    search_intent: Literal["informational", "commercial"] = "informational"
    suggested_word_count: Optional[int] = 200

class Outline(BaseModel):
    title: str = Field(description="SEO-optimized article title.")
    brief: str = Field(description="Article goal and value proposition.")
    sections: conlist(Section, min_length=4, max_length=8)
    faqs: Optional[List[str]] = Field(description="FAQ questions for schema.")
    target_audience: List[str]
    tone: Literal["Professional", "Conversational", "Authoritative"]
    keywords_to_include: conlist(str, min_length=1)
