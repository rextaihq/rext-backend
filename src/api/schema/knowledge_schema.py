from pydantic import BaseModel, HttpUrl, Field, constr
from typing import Optional, List
from uuid import UUID
from datetime import datetime
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
        description="Main content themes or pillars",
        example=["Sustainability", "Fashion Trends", "Eco-lifestyle"]
    )
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
