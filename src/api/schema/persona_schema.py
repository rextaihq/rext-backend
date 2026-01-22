from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class PersonaExtract(BaseModel):
    """Single persona extracted from website content."""
    name: str = Field(
        ...,
        description="Persona name or title",
        example="Tech-Savvy Professional"
    )
    description: Optional[str] = Field(
        None,
        description="Brief description of the persona",
        example="Early adopter seeking efficiency and innovation"
    )
    
    # E-E-A-T professional fields (for expert/author personas)
    full_name: Optional[str] = Field(
        None,
        description="Full professional name",
        example="Dr. Sarah Mitchell"
    )
    professional_title: Optional[str] = Field(
        None,
        description="Professional title or credentials",
        example="Board-Certified Dermatologist"
    )
    areas_of_expertise: Optional[str] = Field(
        None,
        description="Areas of expertise (comma-separated)",
        example="Dermatology, Skin Cancer Detection, Cosmetic Procedures"
    )
    tone_of_voice: Optional[str] = Field(
        None,
        description="Tone of voice style",
        example="Professional, Empathetic, Evidence-based"
    )
    bio: Optional[str] = Field(
        None,
        description="Brief professional biography",
        example="Board-certified dermatologist with 15 years of experience..."
    )
    linkedin_url: Optional[str] = Field(
        None,
        description="LinkedIn profile URL",
        example="https://linkedin.com/in/sarahmitchell"
    )
    
    # User persona fields
    demographics: Optional[str] = Field(
        None,
        description="Demographic information (age, location, income, etc.)",
        example="25-40 years old, urban areas, middle to high income"
    )
    pain_points: Optional[str] = Field(
        None,
        description="Key challenges and pain points this persona faces",
        example="Time constraints, information overload, lack of integration"
    )
    goals: Optional[str] = Field(
        None,
        description="Primary goals and objectives",
        example="Stay competitive, optimize workflow, reduce operational costs"
    )
    behaviors: Optional[str] = Field(
        None,
        description="Behavioral patterns and characteristics",
        example="Research-driven, data-oriented, values authenticity"
    )


class PersonaCreate(BaseModel):
    """Schema for creating a new persona manually."""
    name: str = Field(..., min_length=1, max_length=255, description="Persona name")
    description: Optional[str] = Field(None, description="Brief description")
    
    # E-E-A-T fields
    full_name: Optional[str] = Field(None, max_length=255)
    professional_title: Optional[str] = Field(None, max_length=255)
    areas_of_expertise: Optional[str] = Field(None)
    tone_of_voice: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    
    # User persona fields
    demographics: Optional[str] = Field(None)
    pain_points: Optional[str] = Field(None)
    goals: Optional[str] = Field(None)
    behaviors: Optional[str] = Field(None)


class PersonaUpdate(BaseModel):
    """Schema for updating an existing persona."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None)
    
    # E-E-A-T fields
    full_name: Optional[str] = Field(None, max_length=255)
    professional_title: Optional[str] = Field(None, max_length=255)
    areas_of_expertise: Optional[str] = Field(None)
    tone_of_voice: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    
    # User persona fields
    demographics: Optional[str] = Field(None)
    pain_points: Optional[str] = Field(None)
    goals: Optional[str] = Field(None)
    behaviors: Optional[str] = Field(None)


class PersonaResponse(BaseModel):
    """Schema for persona API responses."""
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str]
    
    # E-E-A-T fields
    full_name: Optional[str]
    professional_title: Optional[str]
    areas_of_expertise: Optional[str]
    tone_of_voice: Optional[str]
    bio: Optional[str]
    linkedin_url: Optional[str]
    
    # User persona fields
    demographics: Optional[str]
    pain_points: Optional[str]
    goals: Optional[str]
    behaviors: Optional[str]
    
    created_at: str
    updated_at: Optional[str]
    
    class Config:
        from_attributes = True

