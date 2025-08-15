from typing_extensions import TypedDict ,Dict, List, Annotated
from langgraph.graph.message import add_messages
from langchain_core.documents import Document
from src.utils.helper import merge_evaluations
#  define the evulation creteria
from pydantic import BaseModel, Field
from typing import List

import operator
class URLCONFIF(BaseModel):
    category:str = "Technology"
    language:str = 'en'
    country:str='pk'
    WP_URL: Dict[str, str]
    keyword :List[str] =['Ai',"ML","DL","Wordpress","WordPress Maintenenace"]
    similarity_threshold:float = 0.3

class EvaluationState(TypedDict):
    rating: Annotated[List[int], operator.add]
    weight: Annotated[List[int], operator.add]
    total_rating: List[int]
    total_weight: List[int]

class AgentState(TypedDict, total=False):
    # workflow configration
    config: URLCONFIF

    # Message state for tools calling
    messages: Annotated[list, add_messages]

    # Basic article data
    articles: Annotated[List[Dict], operator.add]
    filter_articles : List[Dict]
    selected_articles: List[Dict]

    # evaluation
    evaluations: Annotated[Dict[str, EvaluationState],merge_evaluations]

    # Articles Outlines
    outlines : List[Dict]
    approval_feedback : str

    # Summaries section
    blog_content: List[str]
    reference_url: List[str]
    summaries: Annotated[list, operator.add]
    collapsed_summaries: List[Document]
    final_summary: str


    # Blog generation states
    current_blog_index: int
    approved_blogs : List[Dict]
    blog_feedback : str
    generated_blog: str

    # Human feedback or error
    error: Annotated[List[dict], operator.add]


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
from typing import List, Optional
from pydantic import BaseModel, Field

class ImagePlaceholder(BaseModel):
    alt_text: str = Field(..., description="SEO-optimized alt text that accurately describes the image content.")
    suggested_prompt: Optional[str] = Field(None, description="AI-generated text prompt to guide the design team in creating the image for the blog post.")

class Section(BaseModel):
    heading: str = Field(..., description="The title of the section, typically formatted as an H2 or H3 heading.")
    content: str = Field(..., description="The main body text of the section, written in Markdown format.")
    hyperlinks: List[str] = Field(default_factory=list, description="A list of external or internal URLs referenced in this section.")

class BlogArticle(BaseModel):
    title: str = Field(..., description="The primary headline of the blog post.")
    meta_description: str = Field(..., description="A concise, SEO-friendly summary of the blog post (maximum 160 characters).")
    keywords: List[str] = Field(..., description="A list of relevant SEO keywords to improve the discoverability of the blog.")
    introduction: str = Field(..., description="Introductory paragraph(s) that introduce the blog topic, formatted in Markdown.")
    sections: List[Section] = Field(..., description="The main content sections of the blog post, each with its own heading, content, and links.")
    conclusion: str = Field(..., description="A concluding paragraph that wraps up the article, also in Markdown format.")
    references: List[str] = Field(default_factory=list, description="A list of external references that are strictly relevant to the blog title and content.")
    final_image: ImagePlaceholder = Field(..., description="A single image to be placed at the end of the blog, with SEO alt text and an optional AI-generated prompt. Description should be in details simpel and easy to understand so that our ui team will easily understand and make a image")