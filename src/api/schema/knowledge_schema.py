from pydantic import BaseModel, HttpUrl, Field, constr, AliasChoices, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone
from src.api.schema.persona_schema import PersonaExtract
from src.api.schema.audience_schema import AudienceExtract


class TermSubstitution(BaseModel):
    term: str = Field(..., description="Preferred term the brand actually uses", example="track")
    use_instead_of: str = Field(..., description="Term to avoid in favor of the preferred one", example="monitor")


class FieldEvidence(BaseModel):
    """Provenance for one extracted field — value, confidence, and the excerpt it came from.

    Emitted in the same structured-output call as the extracted values
    themselves (no second LLM round-trip). Only cover fields where the
    site gave clear textual evidence — omit fields that were inferred
    rather than directly stated.
    """
    field_name: str = Field(..., description="Name of the extracted field this evidence supports", example="brand_name")
    excerpt: str = Field(..., description="Short verbatim excerpt from the source content supporting this value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence, 0-1")

# -------------------------------------
# Knowledge Base Schema
# -------------------------------------
class KnowledgeBaseCreateSchema(BaseModel):
    """Schema for creating a knowledge base"""
    name: constr(min_length=1, max_length=255) = Field(
        ...,
        description="Name of the knowledge base",
        example="Product Documentation"
    )
    description: Optional[str] = Field(
        None,
        description="Optional description of the knowledge base",
        example="Contains all product-related documentation and guides"
    )


class KnowledgeBaseUpdateSchema(BaseModel):
    """Schema for updating a knowledge base"""
    name: Optional[constr(min_length=1, max_length=255)] = Field(
        None,
        description="Name of the knowledge base",
        example="Updated Product Documentation"
    )
    description: Optional[str] = Field(
        None,
        description="Description of the knowledge base",
        example="Updated description"
    )


class KnowledgeBaseResponseSchema(BaseModel):
    """Schema for knowledge base response"""
    id: UUID = Field(..., description="Knowledge base ID")
    workspace_id: UUID = Field(..., description="Workspace ID")
    name: str = Field(..., description="Knowledge base name")
    description: Optional[str] = Field(None, description="Knowledge base description")
    type: str = Field(..., description="Type: default or custom")
    items_count: int = Field(0, description="Total number of knowledge items")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        from_attributes = True


# -------------------------------------
# Brand Voice Schema
# -------------------------------------
class BrandSchema(BaseModel):
    brand_name: str | None = Field(
        default=None,
        max_length=255,
        description="The brand/product's actual name — used verbatim in generated content, never inferred from the workspace name",
        example="Everlane"
    )
    about: str | None = Field(
        default=None,
        description="Brief description about the brand",
        example="We are a sustainable fashion brand focusing on eco-friendly clothing."
    )
    customer_profile: str | None = Field(
        default=None,
        description="Details about target customers",
        example="Environmentally conscious millennials and Gen Z."
    )
    selling_position: str | None = Field(
        default=None,
        description="Unique selling proposition of the brand",
        example="Affordable eco-friendly fashion for young adults."
    )
    target_audience: List[str] = Field(
        default_factory=list,
        description="List of target audience segments",
        example=["Students", "Young Professionals", "Eco-conscious Consumers"]
    )
    competitors: List[str] = Field(
        default_factory=list,
        description="Real, named market competitors (brand/company names only, not URLs, partners, or clients)",
        example=["Patagonia", "Everlane"]
    )
    content_pillar: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("content_pillar", "content_strategy"),
        description="Main content pillars or strategy themes",
        example=["Sustainability", "Fashion Trends", "Eco-lifestyle"]
    )

    # -- Website classification --
    website_type: Optional[str] = Field(
        default=None,
        description=(
            "Business-model classification of the site. One of: saas, ecommerce, agency, "
            "personal_blog, news_media, documentation, knowledge_base, educational, government, "
            "healthcare, finance, legal, non_profit, community, business_services, other."
        ),
        example="saas",
    )
    website_type_confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Confidence in the website_type classification",
    )

    # -- Voice / style (was the flat 'brand_voice' adjective list; now structured) --
    tone_attributes: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("tone_attributes", "brand_voice"),
        description="Tone and style adjectives (e.g. Friendly, Inspirational, Authentic)",
        example=["Friendly", "Inspirational", "Authentic"]
    )
    formality_level: Optional[str] = Field(
        default=None,
        description="One of: very_casual, casual, neutral, formal, very_formal",
    )
    point_of_view: Optional[str] = Field(
        default=None,
        description="One of: first_singular, first_plural, second, third",
    )
    preferred_terms: List[TermSubstitution] = Field(
        default_factory=list,
        description="Exact preferred vocabulary the brand uses, if stated or clearly evidenced (e.g. always says 'track' never 'monitor')",
    )
    banned_terms: List[str] = Field(
        default_factory=list,
        description="Words/phrases the brand explicitly avoids, if evidenced",
    )
    cta_style: Optional[str] = Field(
        default=None,
        description="Short description of how the brand phrases calls-to-action, if evidenced",
    )

    model_config = ConfigDict(populate_by_name=True)

    personas: List[PersonaExtract] = Field(
        default_factory=list,
        description="Author/Expert personas - REAL PEOPLE from the website (founders, authors, team members, experts). NOT customer personas.",
        example=[{
            "name": "Mobheen Abdullah",
            "description": "Founder & CEO specializing in sustainable fashion",
            "full_name": "Mobheen Abdullah",
            "professional_title": "Founder & Chief Executive Officer",
            "areas_of_expertise": "Sustainable Fashion, E-commerce, Brand Strategy",
            "writing_voice": "Passionate, Authentic, Educational",
            "bio": "Mobheen Abdullah founded the company in 2020 with a mission to make sustainable fashion accessible...",
            "linkedin_url": "https://linkedin.com/in/mobheenabdullah"
        }]
    )
    audience_segments: List[AudienceExtract] = Field(
        default_factory=list,
        description="Buyer/reader audience segments, only if clearly evidenced by the site (customer_profile/target_audience already cover the lightweight case — only add a segment here if there is real additional detail to capture).",
    )
    evidence: List[FieldEvidence] = Field(
        default_factory=list,
        description="Provenance for the fields above — one entry per field with clear textual support. Omit fields you inferred without direct evidence.",
    )


# -------------------------------------
# -------------------------------------
# Text Knowledge Schema
# -------------------------------------
class TextKnowledgeSchema(BaseModel):
    content: constr(min_length=10, max_length=5000) = Field(
        ...,
        description="Text content to store as knowledge",
        example="AI can help automate customer service, improve personalization, and optimize marketing strategies."
    )
    workspace_id: UUID = Field(
        ...,
        description="Workspace identifier",
        example="123e4567-e89b-12d3-a456-426614174000"
    )


class TextKnowledgeResponseSchema(BaseModel):
    """Schema for text knowledge response"""
    id: UUID = Field(..., description="Knowledge item ID")
    workspace_id: UUID = Field(..., description="Workspace ID")
    knowledge_base_id: UUID = Field(..., description="Knowledge base ID")
    title: str = Field(..., description="Knowledge title")
    content: str = Field(..., description="Full text content")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        from_attributes = True


# -------------------------------------
# Web Knowledge Schema
# -------------------------------------
class WebKnowledgeSchema(BaseModel):
    url: HttpUrl = Field(
        ...,
        description="Add a URL you want to include in your knowledge",
        example="https://example.com"
    )
    workspace_id: UUID = Field(
        ...,
        description="Workspace identifier",
        example="123e4567-e89b-12d3-a456-426614174000"
    )


class WebKnowledgeResponseSchema(BaseModel):
    """Schema for web knowledge response"""
    id: UUID = Field(..., description="Knowledge item ID")
    workspace_id: UUID = Field(..., description="Workspace ID")
    knowledge_base_id: UUID = Field(..., description="Knowledge base ID")
    url: str = Field(..., description="Scraped URL")
    title: Optional[str] = Field(None, description="Page title")
    status: str = Field(..., description="Training status")
    char_count: int = Field(0, description="Character count")
    word_count: int = Field(0, description="Word count")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        from_attributes = True


# -------------------------------------
# File Knowledge Schema
# -------------------------------------
class FileKnowledgeResponseSchema(BaseModel):
    """Schema for file knowledge response"""
    id: UUID = Field(..., description="Knowledge item ID")
    workspace_id: UUID = Field(..., description="Workspace ID")
    knowledge_base_id: UUID = Field(..., description="Knowledge base ID")
    file_name: str = Field(..., description="Name of the file")
    file_type: str = Field(..., description="MIME type or extension")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="Exact MIME type")
    chunk_count: int = Field(0, description="Number of text chunks")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    class Config:
        from_attributes = True
