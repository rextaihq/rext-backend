from pydantic import BaseModel, HttpUrl,Field,constr
from typing import Optional,List

# Knowledge Schema
class KnowledgeSchema(BaseModel):
    title: Optional[str] = None
    description: str
    url: Optional[HttpUrl] = None

# Brand Voice Schema
class BrandSchema(BaseModel):
    about: Optional[str] = Field(default=None, description="Brief description about the brand")
    customer_profile: Optional[str] = Field(default=None, description="Details about target customers")
    selling_position: Optional[str] = Field(default=None, description="Unique selling proposition of the brand")
    target_audience: Optional[List[str]] = Field(default_factory=list, description="List of target audience segments")
    brand_voice: Optional[List[str]] = Field(default_factory=list, description="Tone and style of communication")
    competitors: Optional[List[str]] = Field(default_factory=list, description="List of competitors")
    content_pillar: Optional[List[str]] = Field(default_factory=list, description="Main content themes or pillars")


class TextKnowledgeSchema(BaseModel):
    content: constr(min_length=10, max_length=5000)
    workspace_id: str
