from pydantic import BaseModel, HttpUrl

class CanonicalTagRequest(BaseModel):
    url: HttpUrl


class CanonicalTagResponse(BaseModel):
    canonical_tag: str
    url: str
    normalized_url: str


class HreflangEntry(BaseModel):
    language: str | None = None
    region: str | None = None
    url: HttpUrl


class HreflangRequest(BaseModel):
    default_url: HttpUrl
    language_region_urls: list[HreflangEntry]
    include_x_default: bool = True
    output_format: str = "html"  # "html" or "sitemap"


class HreflangResponse(BaseModel):
    hreflang_tags: str
    warnings: list[str] | None = None
