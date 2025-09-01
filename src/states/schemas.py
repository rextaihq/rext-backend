from typing import List, Optional
from pydantic import BaseModel, Field
from uuid import UUID

# =========Topic Generation Schema=========
class TopicScore(BaseModel):
    relevance: float = Field(..., ge=0, le=1, description="Relevance score (0-1)")
    freshness: float = Field(..., ge=0, le=1, description="Freshness score (0-1)")
    novelty: float = Field(..., ge=0, le=1, description="Novelty score (0-1)")

class TopicGeneration(BaseModel):
    title: str
    angle: str
    channel_fit: List[str]
    audience_fit: List[str]
    scores: TopicScore
    why_it_works: str
    tags: List[str]

class TopicGenerationList(BaseModel):
    topics: List[TopicGeneration]


# ===== Blog Generation Schemas =====
class ImagePlaceholder(BaseModel):
    alt_text: str = Field(..., description="SEO-optimized alt text that accurately describes the image content.")
    suggested_prompt: Optional[str] = Field(None, description="AI-generated text prompt for designers.")


class Section(BaseModel):
    heading: str = Field(..., description="The title of the section (H2/H3).")
    content: str = Field(..., description="The body text in Markdown.")
    hyperlinks: List[str] = Field(default_factory=list, description="URLs referenced in this section.")


class BlogArticle(BaseModel):
    title: str
    meta_description: str
    keywords: List[str]
    introduction: str
    sections: List[Section]
    conclusion: str
    references: List[str] = []
    final_image: ImagePlaceholder


# ===== Evaluation Schema =====
class Evaluation(BaseModel):
    rating: int = Field(..., ge=0, le=10, description="Rating of the blog (0-10)")
    weight: int = Field(..., ge=0, le=10, description="Importance weight (0-10)")


# ===== Article Outline =====
class OutlineSection(BaseModel):
    heading: str
    bullet_points: List[str]


class ArticleOutline(BaseModel):
    title: str
    introduction: str
    sections: List[OutlineSection]
    conclusion: str


# ===== Query/Title Models =====
class RewriterTitle(BaseModel):
    refine_title: str = Field(..., description="Refined title for retrieval.")


class QueryDecomposer(BaseModel):
    compose_title: List[str] = Field(
        ..., description="List (max 5) of refined sub-queries for retrieval."
    )
