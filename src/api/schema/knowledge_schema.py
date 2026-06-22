from pydantic import BaseModel, HttpUrl, Field, constr, AliasChoices, ConfigDict
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone
from src.api.schema.persona_schema import PersonaExtract

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
    brand_voice: List[str] = Field(
        default_factory=list,
        description="Tone and style of communication",
        example=["Friendly", "Inspirational", "Authentic"]
    )
    competitors: List[str] = Field(
        default_factory=list,
        description="List of competitors",
        example=["Patagonia", "Everlane"]
    )
    content_pillar: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("content_pillar", "content_strategy"),
        description="Main content pillars or strategy themes",
        example=["Sustainability", "Fashion Trends", "Eco-lifestyle"]
    )
    # ---- PLC (Product-Led Content) fields ----
    product_name: str | None = Field(
        default=None,
        description="The brand's product or company name as it should appear in content",
        example="Rext"
    )
    product_vocabulary: List[dict] = Field(
        default_factory=list,
        description="Brand-specific vocabulary rules: preferred term vs term to avoid",
        example=[{"use": "members", "not": "users"}, {"use": "workspace", "not": "account"}]
    )
    forbidden_words: List[str] = Field(
        default_factory=list,
        description="Words and phrases the brand never uses in content",
        example=["cheap", "basic", "simple solution", "just"]
    )
    brand_ctas: List[str] = Field(
        default_factory=list,
        description="Exact call-to-action phrases the brand uses",
        example=["Start your free trial", "Book a demo", "See it in action"]
    )
    key_differentiators: List[str] = Field(
        default_factory=list,
        description="What makes the product uniquely better than alternatives",
        example=["Only AI content tool with built-in SEO scoring", "Publishes directly to WordPress & Shopify"]
    )
    tone_examples: List[dict] = Field(
        default_factory=list,
        description="Before/after tone examples showing brand voice in practice",
        example=[{"like": "We built this because we were tired of content that ranks but doesn't convert.", "not_like": "Our platform leverages cutting-edge AI to optimize your content strategy."}]
    )
    use_cases: List[dict] = Field(
        default_factory=list,
        description="Product use cases: the pain point and how the product solves it",
        example=[{"pain": "Spending hours writing content that never ranks", "solution": "Rext generates SEO-optimized drafts in minutes, pre-loaded with keyword clusters and competitor gaps"}]
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
            "tone_of_voice": "Passionate, Authentic, Educational",
            "bio": "Mobheen Abdullah founded the company in 2020 with a mission to make sustainable fashion accessible...",
            "linkedin_url": "https://linkedin.com/in/mobheenabdullah"
        }]
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
