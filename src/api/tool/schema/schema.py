from pydantic import BaseModel,  Field, field_validator,HttpUrl
from typing import List, Optional
import re

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

#Schema  Generator model request
class SchemaRequest(BaseModel):
    # Required fields
    schema_type: str = Field(...,min_length=1, description="Schema.org type (e.g. Article, Product)")
    name: str = Field(...,min_length=1,description="Main title or name of the schema item")

    # Optional fields
    description: Optional[str] = Field(
        None, description="Short description or summary"
    )
    url: Optional[str] = Field(None, description="Canonical URL of the page")
    image_url: Optional[str] = Field(None, description="Image URL for the schema")
    author_name: Optional[str] = Field(None, description="Author name")
    date_published: Optional[str] = Field(
        None, description="Publish date in MM/DD/YYYY format"
    )

    @field_validator('url', 'image_url')
    @classmethod
    def validate_url(cls, v, info):
        # Treat empty string as None for optional fields
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        
        # URL regex pattern
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        
        if not url_pattern.match(v):
            raise ValueError(
                f'{info.field_name} must be a valid URL starting with http:// or https://. '
                f'Got: {v}'
            )
        return v

    @field_validator('date_published')
    @classmethod
    def validate_date(cls, v):
        # Treat empty string as None for optional fields
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        
        # Validate MM/DD/YYYY date format with proper month (01-12) and day (01-31) ranges
        date_pattern = re.compile(r'^(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])/\d{4}$')
        if not date_pattern.match(v):
            raise ValueError(
                'date_published must be in MM/DD/YYYY format (e.g., 01/20/2026). '
                f'Got: {v}'
            )
        return v
    
# Readability Tool Model
class ReadabilityRequest(BaseModel):
    content: str = Field(..., min_length=10,description="The text content you want to analyze for readability. Minimum 10 characters.")



class ReadabilityResponse(BaseModel):
    readability_score: float
    grade_level: float
    sentence_complexity: float
    reading_level: str
    word_count: int
    sentence_count: int

# Idea Generator tool model
class IdeaGeneratorRequest(BaseModel):
    topic: str = Field(..., description="The main topic to generate ideas for")
    content_type: str = Field(..., description="The type of content (e.g., blog, social media piece, video script)")
    ideas_count: int = Field(3, ge=1, le=20, description="Number of ideas to generate (1-20)")


class IdeaGeneratorResponse(BaseModel):
    topic: str
    ideas: List[str]

#.............

class CanonicalTagRequest(BaseModel):
    url: str  # Using str to avoid Pydantic strict URL validation issues if desired, or duplicate validation logic


class CanonicalTagResponse(BaseModel):
    canonical_tag: str
    url: str
    normalized_url: str


class HreflangEntry(BaseModel):
    language: str | None = None
    region: str | None = None
    url: str


class HreflangRequest(BaseModel):
    default_url: str
    language_region_urls: list[HreflangEntry]
    include_x_default: bool = True
    output_format: str = "html"  # "html" or "sitemap"


class HreflangResponse(BaseModel):
    hreflang_tags: str
    warnings: list[str] | None = None
    
class TitleRequest(BaseModel):
    keyword: str
    topic: str
    brand: str
    tone: str
    
class TitleResponse(BaseModel):
    titles: List[str]

# -----------------------------
# FAQ Generator Tool Models
# -----------------------------

class FAQRequest(BaseModel):
    topic: str = Field(..., description="The main topic to generate FAQs for")
    faq_count: int = Field(5,ge=1,  le=20, description="Number of FAQs to generate (1-20)")
    tone: str = Field("simple", description="Tone of the FAQs (e.g., simple, professional, friendly)")

class FAQItem(BaseModel):
    question: str = Field(..., description="The question text")
    answer: str = Field(..., description="The answer text for the question")

class FAQResponse(BaseModel):
    topic: str = Field(..., description="The topic for which FAQs were generated")
    faqs: List[FAQItem] = Field(..., description="List of generated FAQ question-answer pairs")