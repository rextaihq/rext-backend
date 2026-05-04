from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID


class PersonaExtract(BaseModel):
    """Author/Expert persona extracted from website content.
    
    This represents REAL PEOPLE who create content, run the business, or are mentioned as experts.
    DO NOT use this for customer/user personas or target audience segments.
    
    Examples: Blog authors, founders, team members, consultants, experts
    """
    name: str = Field(
        ...,
        description="Person's actual name (e.g., 'Mobheen Abdullah', 'Dr. Sarah Mitchell')",
        example="Mobheen Abdullah"
    )
    description: Optional[str] = Field(
        None,
        description="Brief description of the person's role or expertise",
        example="Founder & CEO with expertise in sustainable fashion"
    )
    avatar_url: Optional[str] = Field(
        None,
        description="URL to the persona's avatar image",
        example="https://example.com/avatars/persona.jpg"
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
    areas_of_expertise: List[str] = Field(
        default_factory=list,
        description="Areas of expertise",
        example=["Dermatology", "Skin Cancer Detection"]
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
        description="Key challenges and pain points this persona faces, comma-separated",
        example="Time constraints, Information overload"
    )
    goals: Optional[str] = Field(
        None,
        description="Primary goals and objectives, comma-separated",
        example="Stay competitive, Optimize workflow"
    )
    behaviors: Optional[str] = Field(
        None,
        description="Behavioral patterns and characteristics, comma-separated",
        example="Research-driven, Data-oriented"
    )


class PersonaCreate(BaseModel):
    """Schema for creating a new persona manually."""
    name: str = Field(..., min_length=1, max_length=255, description="Persona name")
    description: Optional[str] = Field(None, description="Brief description")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")
    
    # E-E-A-T fields
    full_name: Optional[str] = Field(None, max_length=255)
    professional_title: Optional[str] = Field(None, max_length=255)
    areas_of_expertise: Optional[List[str]] = Field(default_factory=list)
    tone_of_voice: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    
    # User persona fields
    demographics: Optional[str] = Field(None)
    pain_points: Optional[List[str]] = Field(default_factory=list)
    goals: Optional[List[str]] = Field(default_factory=list)
    behaviors: Optional[List[str]] = Field(default_factory=list)


class PersonaUpdate(BaseModel):
    """Schema for updating an existing persona."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None)
    avatar_url: Optional[str] = Field(None)
    
    # E-E-A-T fields
    full_name: Optional[str] = Field(None, max_length=255)
    professional_title: Optional[str] = Field(None, max_length=255)
    areas_of_expertise: Optional[List[str]] = Field(None)
    tone_of_voice: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    
    # User persona fields
    demographics: Optional[str] = Field(None)
    pain_points: Optional[List[str]] = Field(None)
    goals: Optional[List[str]] = Field(None)
    behaviors: Optional[List[str]] = Field(None)


class PersonaResponse(BaseModel):
    """Schema for persona API responses."""
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str]
    avatar_url: Optional[str]
    
    # E-E-A-T fields
    full_name: Optional[str]
    professional_title: Optional[str]
    areas_of_expertise: List[str] = []
    tone_of_voice: Optional[str] = None
    bio: Optional[str] = None
    linkedin_url: Optional[str] = None
    
    # User persona fields
    demographics: Optional[str] = None
    pain_points: List[str] = []
    goals: List[str] = []
    behaviors: List[str] = []
    
    created_at: str
    updated_at: Optional[str]
    
    class Config:
        from_attributes = True
