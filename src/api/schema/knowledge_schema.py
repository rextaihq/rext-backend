from pydantic import BaseModel, HttpUrl, Field, constr
from typing import Optional, List
from uuid import UUID

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
