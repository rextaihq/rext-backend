from pydantic import BaseModel, HttpUrl, Field, field_validator,validator
from typing import List, Optional, Union
import re

# Word Counter Schemas
class TextInput(BaseModel):
    text: str = Field(..., min_length=1)

class TextMetricsOutput(BaseModel):
    words: int
    characters: int
    sentences: int
    paragraphs: int
    min_read: int

# Meta Description Schemas
class MetaDescriptionRequest(BaseModel):
    page_title: str
    target_keywords: List[str]

class MetaDescriptionValidation(BaseModel):
    length: int
    is_optimal_length: bool
    character_count: str
    warnings: List[str]

class MetaDescriptionResponse(BaseModel):
    meta_description: str
    validation: MetaDescriptionValidation

# Broken Link Schemas
class BrokenLinkRequest(BaseModel):
    url: HttpUrl = Field(..., description="URL to check for broken link")

class BrokenLinkResponse(BaseModel):
    working: bool

# Title Tag Schemas
class TitleRequest(BaseModel):
    keyword: str
    topic: str
    brand: str
    tone: str

class TitleResponse(BaseModel):
    titles: List[str]

# Schema Generator Schemas
class SchemaRequest(BaseModel):
    schema_type: str = Field(..., min_length=1, description="Schema.org type (e.g. Article, Product)")
    name: str = Field(..., min_length=1, description="Main title or name of the schema item")
    description: Optional[str] = Field(None, description="Short description or summary")
    url: Optional[str] = Field(None, description="Canonical URL of the page")
    image_url: Optional[str] = Field(None, description="Image URL for the schema")
    author_name: Optional[str] = Field(None, description="Author name")
    date_published: Optional[str] = Field(None, description="Publish date in MM/DD/YYYY format")

    @field_validator('url', 'image_url')
    @classmethod
    def validate_url(cls, v, info):
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        url_pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        if not url_pattern.match(v):
            raise ValueError(f'{info.field_name} must be a valid URL. Got: {v}')
        return v

    @field_validator('date_published')
    @classmethod
    def validate_date(cls, v):
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        date_pattern = re.compile(r'^(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/\d{4}$')
        if not date_pattern.match(v):
            raise ValueError('date_published must be in MM/DD/YYYY format. Got: {v}')
        return v

# Readability Checker Schemas
class ReadabilityRequest(BaseModel):
    content: str = Field(..., min_length=10, description="The text content to analyze. Minimum 10 characters.")

class ReadabilityResponse(BaseModel):
    readability_score: float
    grade_level: float
    sentence_complexity: float
    reading_level: str
    word_count: int
    sentence_count: int

# Idea Generator Schemas
class IdeaGeneratorRequest(BaseModel):
    topic: str = Field(...,description="The main topic to generate ideas for")
    content_type: str = Field(..., description="The type of content")
    ideas_count: int = Field(3, ge=1, le=20, description="Number of ideas to generate (1-20)")

class IdeaGeneratorResponse(BaseModel):
    topic: str
    ideas: List[str]

# Canonical Tag Schemas
class CanonicalTagRequest(BaseModel):
    url: Union[HttpUrl, str]

class CanonicalTagResponse(BaseModel):
    canonical_tag: str
    url: str
    normalized_url: str

# Hreflang Tag Schemas
class HreflangEntry(BaseModel):
    language: Optional[str] = None
    region: Optional[str] = None
    url: Union[HttpUrl, str]

class HreflangRequest(BaseModel):
    language_region_urls: List[HreflangEntry]
    default_url: Union[HttpUrl, str]
    include_x_default: bool = True
    output_format: str = "html"

class HreflangResponse(BaseModel):
    hreflang_tags: str
    warnings: list[str] | None = None

# -----------------------------
# FAQ Generator Tool Models
# -----------------------------

class FAQRequest(BaseModel):
    topic: str = Field(..., description="The main topic to generate FAQs for")
    faq_count: int = Field(5,ge=1,  le=20, description="Number of FAQs to generate (1-20)")
    tone: str = Field("simple", description="Tone of the FAQs (e.g., simple, professional, friendly)")
    @validator("topic")
    def topic_must_not_be_empty(cls, v):
        if not v.strip():  # prevents empty strings or spaces-only
            raise ValueError("Topic must not be empty")
        return v
class FAQItem(BaseModel):
    question: str = Field(..., description="The question text")
    answer: str = Field(..., description="The answer text for the question")

class FAQResponse(BaseModel):
    topic: str = Field(..., description="The topic for which FAQs were generated")
    faqs: List[FAQItem] = Field(..., description="List of generated FAQ question-answer pairs")

# Robots.txt Schemas
class RobotsTxtRequest(BaseModel):
    user_agent: str = Field(default="*", description="User-agent identifying the crawler")
    allow: List[str] = Field(default_factory=list, description="List of allowed paths")
    disallow: List[str] = Field(default_factory=list, description="List of disallowed paths")
    sitemap_url: Optional[Union[HttpUrl, str]] = Field(default=None, description="Optional Sitemap URL")

class RobotsTxtResponse(BaseModel):
    robots_txt: str

# Grammar Checker Schemas
class GrammarIssue(BaseModel):
    original_phrase: str
    suggested_correction: str
    issue_type: str

class GrammarCheckerRequest(BaseModel):
    text: str

class GrammarCheckerResponse(BaseModel):
    corrected_text: str
    issues: List[GrammarIssue]

# Hook Generator Schemas
class HookGeneratorRequest(BaseModel):
    topic_description: str = Field(..., description="The description of the topic for the content")
    goal_of_content: str = Field(..., description="The goal or purpose of the content")
    number_of_variations: int = Field(3, ge=1, le=10, description="The number of variations to generate")

class HookGeneratorResponse(BaseModel):
    topic: str
    hooks: List[str]

# SEO Blog Title Generator Schemas
class SEOBlogTitleRequest(BaseModel):
    keyword: str = Field(..., description="The main keyword to generate blog titles for")
    number_of_topics: int = Field(5, ge=1, le=20, description="The number of topics to generate")
    min_words: int = Field(5, ge=1, description="Minimum number of words per title")
    max_words: int = Field(15, ge=1, description="Maximum number of words per title")

class SEOBlogTitleResponse(BaseModel):
    keyword: str
    blog_titles: List[str]
