from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional

# Word Counter Schemas
class TextInput(BaseModel):
    # Ensures text is not just an empty string at the schema level
    text: str = Field(..., min_length=1)

class TextMetricsOutput(BaseModel):
    words: int
    characters: int
    sentences: int
    paragraphs: int
    min_read: int

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
    schema_type: str
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    author_name: Optional[str] = None
    date_published: Optional[str] = None

# Readability Checker Schemas
class ReadabilityRequest(BaseModel):
    content: str

class ReadabilityResponse(BaseModel):
    readability_score: float
    grade_level: float
    sentence_complexity: float
    word_count: int
    sentence_count: int
    reading_level: str

# Canonical Tag Schemas
class CanonicalTagRequest(BaseModel):
    url: HttpUrl

class CanonicalTagResponse(BaseModel):
    canonical_tag: str
    url: str
    normalized_url: str

# Hreflang Tag Schemas
class HreflangEntry(BaseModel):
    url: HttpUrl
    language: Optional[str] = None
    region: Optional[str] = None

class HreflangRequest(BaseModel):
    language_region_urls: List[HreflangEntry]
    default_url: HttpUrl
    include_x_default: bool = True
    output_format: str = "html"

class HreflangResponse(BaseModel):
    hreflang_tags: str
    warnings: Optional[List[str]] = None

# Robots.txt Schemas
class RobotsTxtRequest(BaseModel):
    user_agent: str = Field(default="*", description="User-agent identifying the crawler")
    allow: List[str] = Field(default_factory=list, description="List of allowed paths")
    disallow: List[str] = Field(default_factory=list, description="List of disallowed paths")
    sitemap_url: Optional[HttpUrl] = Field(default=None, description="Optional Sitemap URL")

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
