from pydantic import BaseModel, Field, HttpUrl


class CanonicalTagRequest(BaseModel):
    """Request for generating a canonical tag."""

    url: HttpUrl = Field(description="The primary URL for which to generate the canonical tag.")


class CanonicalTagResponse(BaseModel):
    """Response structure for a canonical tag."""

    canonical_tag: str = Field(description="The generated HTML canonical link tag.")
    url: str = Field(description="The original input URL.")
    normalized_url: str = Field(description="The normalized version of the URL used for the tag.")


class HreflangEntry(BaseModel):
    """Represents a single language/region mapping for a URL."""

    language: str | None = Field(None, description="ISO 639-1 language code (e.g., 'en').")
    region: str | None = Field(None, description="ISO 3166-1 Alpha-2 region code (e.g., 'US').")
    url: HttpUrl = Field(description="The URL for this language/region version.")


class HreflangRequest(BaseModel):
    """Request for generating multiple hreflang tags."""

    default_url: HttpUrl = Field(description="The default URL for x-default.")
    language_region_urls: list[HreflangEntry] = Field(
        description="List of language/region to URL mappings."
    )
    include_x_default: bool = Field(True, description="Whether to include the x-default tag.")
    output_format: str = Field("html", description="The output format: 'html' or 'sitemap'.")


class HreflangResponse(BaseModel):
    """Response structure for generated hreflang tags."""

    hreflang_tags: str = Field(
        description="The generated hreflang tags as a single string (one per line)."
    )
    warnings: list[str] | None = Field(
        None, description="SEO warnings related to the generation process."
    )


class SimpleHreflangResponse(BaseModel):
    """Structured output for the LLM to return only the tags."""

    tags: list[str] = Field(description="List of generated hreflang tags.")
