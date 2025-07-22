from typing import TypedDict,Dict,List,Annotated, Optional
from langgraph.graph.message import add_messages
#  define the evulation creteria
from pydantic import BaseModel, Field
from typing import List

import operator

class AgentState(TypedDict, total=False):
    # Basic article data
    articles: List[Dict]
    wordpress_articles: List[Dict]
    combine_articles: List[Dict]
    selected_articles: List[Dict]

    # Relevance evaluation
    relevance_rating: Annotated[List[int], operator.add]
    relevance_weight: Annotated[List[int], operator.add]

    # Trend evaluation
    trend_rating: Annotated[List[int], operator.add]
    trend_weight: Annotated[List[int], operator.add]

    # Controversy evaluation
    controversy_rating: Annotated[List[int], operator.add]
    controversy_weight: Annotated[List[int], operator.add]

    # Uniqueness evaluation
    uniqueness_rating: Annotated[List[int], operator.add]
    uniqueness_weight: Annotated[List[int], operator.add]

    reader_rating: Annotated[List[int], operator.add]
    reader_weight: Annotated[List[int], operator.add]

    brand_rating: Annotated[List[int], operator.add]
    brand_weight: Annotated[List[int], operator.add]

    actionable_rating: Annotated[List[int], operator.add]
    actionable_weight: Annotated[List[int], operator.add]

    seo_rating: Annotated[List[int], operator.add]
    seo_weight: Annotated[List[int], operator.add]

    total_rating: List[int]
    total_weight: List[int]

    # Articles Outlines
    approved_outlines : List[Dict]
    approval_feedback : str
    current_approval_index: int

    # Blog generation states
    current_blog_index: int
    approved_blogs : List[Dict]
    blog_feedback : str


    # Human feedback or error
    error: str


class Evaluation(BaseModel):
    # feedback: str = Field(..., description="Detailed feedback of the blog")
    rating: int = Field(..., ge=0, le=10, description="Rating of the blog on a scale of 0 to 10")
    weight: int = Field(..., ge=0, le=10, description="Weight/importance of this criterion (0 to 10)")


# 1. Define the output schema for outline
class Section(BaseModel):
    heading: str = Field(..., description="Title of the section")
    bullet_points: List[str] = Field(..., description="List of sub-points under this section")

class ArticleOutline(BaseModel):
    title:str
    introduction: str
    sections: List[Section]
    conclusion: str


# ==============Blog Generation================
class ImagePlaceholder(BaseModel):
    alt_text: str = Field(..., description="SEO-friendly alt text for the image")
    suggested_prompt: Optional[str] = Field(None, description="Optional AI image generation prompt")

class Section(BaseModel):
    heading: str = Field(..., description="Title of the section (H2 or H3)")
    content: str = Field(..., description="Main text content of the section in Markdown")
    hyperlinks: List[str] = Field(default_factory=list, description="List of URLs used in this section")
    images: List[ImagePlaceholder] = Field(default_factory=list, description="Image placeholders for this section")

class BlogArticle(BaseModel):
    title: str = Field(..., description="Main title of the blog post")
    meta_description: str = Field(..., description="Short SEO meta description (max 160 chars)")
    keywords: List[str] = Field(..., description="List of SEO keywords for this article")
    introduction: str = Field(..., description="Introduction paragraph(s) in Markdown")
    sections: List[Section] = Field(..., description="Main body sections of the blog post")
    conclusion: str = Field(..., description="Conclusion section text")
    references: List[str] = Field(default_factory=list, description="List of external reference URLs")