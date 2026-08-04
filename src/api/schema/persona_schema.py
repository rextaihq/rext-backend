from pydantic import BaseModel, Field
from typing import Optional, List


class CredentialExtract(BaseModel):
    credential: str = Field(..., description="Credential/certification name", example="CISSP")
    issuer: Optional[str] = Field(None, description="Issuing body", example="ISC2")
    year: Optional[int] = Field(None, description="Year obtained", example=2021)


class PersonaExtract(BaseModel):
    """Author/Expert persona extracted from website content.

    This represents REAL PEOPLE who create content, run the business, or are mentioned as experts.
    DO NOT use this for customer/user personas or target audience segments — those belong in
    AudienceExtract (see knowledge_schema.py).

    Examples: Blog authors, founders, team members, consultants, experts
    """
    name: str = Field(
        ...,
        description="Person's actual name (e.g., 'Mobheen Abdullah', 'Dr. Sarah Mitchell')",
        example="Mobheen Abdullah"
    )
    source: str = Field(
        ...,
        description=(
            "Where this person was identified on the site. Must be one of: "
            "'founder', 'team_member', 'author', 'expert', or 'testimonial'. "
            "If a person's name appears ONLY as the attribution on a customer testimonial/review/"
            "case-study quote (e.g. 'Jane Doe, Ohio' under a review) and not otherwise as a founder, "
            "team member, author, or expert, do NOT include them as a persona at all — omit them from "
            "the list entirely. The 'testimonial' value is only a fallback safety label for edge cases; "
            "leaving testimonial-only contributors out of the list is always preferred over labeling them."
        ),
        example="founder"
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

    # E-E-A-T professional identity fields (schema.org/Person-aligned)
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
    experience_type: Optional[str] = Field(
        None,
        description=(
            "Google E-E-A-T distinction: 'everyday_experience' (lived through it personally), "
            "'formal_expertise' (credentialed professional), or 'both'. Infer from how the site "
            "describes them — a stated license/degree/certification implies formal_expertise."
        ),
        example="formal_expertise"
    )
    years_of_experience: Optional[int] = Field(
        None,
        description="Years in their field, only if explicitly stated on the site",
        example=12
    )
    credentials: List[CredentialExtract] = Field(
        default_factory=list,
        description="Formal qualifications explicitly stated on the site",
    )
    employer: Optional[str] = Field(
        None,
        description="Current employer/company, if distinct from the brand itself",
    )
    writing_voice: Optional[str] = Field(
        None,
        description="This person's personal tone of voice, if discernible from their writing",
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


class PersonaCreate(BaseModel):
    """Schema for creating a new author persona manually."""
    name: str = Field(..., min_length=1, max_length=255, description="Persona name")
    description: Optional[str] = Field(None, description="Brief description")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")

    full_name: Optional[str] = Field(None, max_length=255)
    professional_title: Optional[str] = Field(None, max_length=255)
    areas_of_expertise: Optional[List[str]] = Field(default_factory=list)
    experience_type: Optional[str] = Field(None, max_length=50)
    years_of_experience: Optional[int] = Field(None)
    credentials: Optional[List[CredentialExtract]] = Field(default_factory=list)
    employer: Optional[str] = Field(None, max_length=255)
    writing_voice: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None)
    linkedin_url: Optional[str] = Field(None, max_length=500)


class PersonaUpdate(BaseModel):
    """Schema for updating an existing author persona."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None)
    avatar_url: Optional[str] = Field(None)

    full_name: Optional[str] = Field(None, max_length=255)
    professional_title: Optional[str] = Field(None, max_length=255)
    areas_of_expertise: Optional[List[str]] = Field(None)
    experience_type: Optional[str] = Field(None, max_length=50)
    years_of_experience: Optional[int] = Field(None)
    credentials: Optional[List[CredentialExtract]] = Field(None)
    employer: Optional[str] = Field(None, max_length=255)
    writing_voice: Optional[str] = Field(None, max_length=255)
    bio: Optional[str] = Field(None)
    linkedin_url: Optional[str] = Field(None, max_length=500)
