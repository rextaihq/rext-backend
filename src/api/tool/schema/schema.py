from pydantic import BaseModel, HttpUrl, Field
from typing import List

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

from pydantic import BaseModel, HttpUrl
from typing import List

class SitemapRequest(BaseModel):
    url: HttpUrl

class SitemapResponse(BaseModel):
    urls: List[HttpUrl]
    sitemap_xml: str
