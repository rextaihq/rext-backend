from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class PersonaExtract(BaseModel):
    """Author/Expert persona extracted from website content.

    This represents REAL PEOPLE who create content, run the business, or are mentioned as experts.
    DO NOT use this for customer/user personas or target audience segments.

    Examples: Blog authors, founders, team members, consultants, experts
    """

    name: str = Field(
        ...,
        description="Person's actual name, copied exactly as the page writes it. Never a placeholder or specimen name.",
        example="Mobheen Abdullah",
    )
    source: Optional[str] = Field(
        None,
        description=(
            "Where this person was identified on the site. Must be one of: "
            "'founder', 'team_member', 'author', 'expert', or 'testimonial'. "
            "If a person's name appears ONLY as the attribution on a customer testimonial/review/"
            "case-study quote, with a city or company after their name, and not otherwise as a founder, "
            "team member, author, or expert, do NOT include them as a persona at all — omit them from "
            "the list entirely. If such a person IS included, they must carry source='testimonial' so "
            "the extraction pipeline can drop them; relabeling a customer as 'expert' or 'team_member' "
            "because their title sounds senior is the failure this field exists to prevent. "
            "Optional here (rather than required) because the workspace brand-voice PUT/save endpoint "
            "accepts personas from the frontend, which doesn't send this field — the automatic "
            "extraction pipeline always populates it regardless."
        ),
        example="founder",
    )
    description: Optional[str] = Field(
        None,
        description="Brief description of the person's role or expertise",
        example="Founder & CEO with expertise in sustainable fashion",
    )
    avatar_url: Optional[str] = Field(
        None,
        description="URL to the persona's avatar image",
        example="https://example.com/avatars/persona.jpg",
    )
    email: Optional[str] = Field(
        None,
        description=(
            "The person's own published email address, if the page "
            "states one. Used to derive a Gravatar when no photograph "
            "was found. Never a shared or departmental inbox."
        ),
        example="writer@example.com",
    )

    # E-E-A-T professional fields (for expert/author personas)
    full_name: Optional[str] = Field(
        None,
        description="Full professional name",
    )
    professional_title: Optional[str] = Field(
        None,
        description="Professional title or credentials",
        example="Board-Certified Dermatologist",
    )
    areas_of_expertise: List[str] = Field(
        default_factory=list,
        description="Areas of expertise",
        example=["Dermatology", "Skin Cancer Detection"],
    )

    @field_validator("areas_of_expertise", mode="before")
    @classmethod
    def _coerce_areas_of_expertise(cls, v):
        """Accept a single comma-separated string too — the workspace brand-voice
        PUT/save endpoint's frontend type allows string | string[] here."""
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    tone_of_voice: Optional[str] = Field(
        None, description="Tone of voice style", example="Professional, Empathetic, Evidence-based"
    )
    bio: Optional[str] = Field(
        None,
        description="Brief professional biography",
        example="Board-certified dermatologist with 15 years of experience...",
    )
    linkedin_url: Optional[str] = Field(
        None, description="LinkedIn profile URL", example="https://linkedin.com/in/sarahmitchell"
    )

    # User persona fields
    demographics: Optional[str] = Field(
        None,
        description="Demographic information (age, location, income, etc.)",
        example="25-40 years old, urban areas, middle to high income",
    )
    pain_points: Optional[str] = Field(
        None,
        description="Key challenges and pain points this persona faces, comma-separated",
        example="Time constraints, Information overload",
    )
    goals: Optional[str] = Field(
        None,
        description="Primary goals and objectives, comma-separated",
        example="Stay competitive, Optimize workflow",
    )
    behaviors: Optional[str] = Field(
        None,
        description="Behavioral patterns and characteristics, comma-separated",
        example="Research-driven, Data-oriented",
    )

    @field_validator("pain_points", "goals", "behaviors", mode="before")
    @classmethod
    def _coerce_list_to_comma_string(cls, v):
        """Accept a list too — the workspace brand-voice PUT/save endpoint's
        frontend type allows string | string[] for these fields."""
        if isinstance(v, (list, tuple, set)):
            return ", ".join(str(item).strip() for item in v if item is not None) or None
        return v


class PersonaAnalysis(BaseModel):
    """One person's profile, analysed from only their own pages on the site.

    Every field is optional: the extraction leaves a field empty when the
    person's pages do not support it rather than writing a plausible guess.
    """

    professional_title: Optional[str] = Field(
        None, description="Role the site gives this person; 'Author' for a byline only"
    )
    bio: Optional[str] = Field(
        None, description="1-2 factual sentences drawn from the supplied pages"
    )
    description: Optional[str] = Field(None, description="One line naming their role and focus")
    areas_of_expertise: List[str] = Field(
        default_factory=list, description="3-6 concrete topics their articles or profile cover"
    )
    tone_of_voice: Optional[str] = Field(
        None, description="2-4 comma-separated adjectives, only from their own articles"
    )
    demographics: Optional[str] = Field(
        None, description="The readers their articles are written for"
    )
    pain_points: Optional[str] = Field(
        None, description="Comma-separated reader problems their articles address"
    )
    goals: Optional[str] = Field(
        None, description="Comma-separated outcomes their articles guide readers toward"
    )
    behaviors: Optional[str] = Field(
        None, description="Comma-separated working methods their articles demonstrate"
    )

    @field_validator("areas_of_expertise", mode="before")
    @classmethod
    def _coerce_areas_of_expertise(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v or []

    @field_validator("pain_points", "goals", "behaviors", mode="before")
    @classmethod
    def _coerce_list_to_comma_string(cls, v):
        if isinstance(v, (list, tuple, set)):
            return ", ".join(str(item).strip() for item in v if item is not None) or None
        return v


class PersonaCreate(BaseModel):
    """Schema for creating a new persona manually."""

    name: str = Field(..., min_length=1, max_length=255, description="Persona name")
    description: Optional[str] = Field(None, description="Brief description")
    avatar_url: Optional[str] = Field(
        None,
        description=(
            "Profile image URL. Set explicitly, this is a custom "
            "image and takes precedence over anything derived."
        ),
    )
    email: Optional[EmailStr] = Field(
        None,
        description=(
            "Email address. A Gravatar is derived from it only when "
            "no custom avatar_url has been set. Validated as an "
            "address rather than a bounded string: it is hashed and "
            "sent to a third party, and a malformed one produces a "
            "hash of nothing and a picture that never resolves."
        ),
    )

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

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_is_none(cls, v):
        """A cleared email field arrives as "" and means no address, not an
        invalid one."""
        return None if isinstance(v, str) and not v.strip() else v


class PersonaUpdate(BaseModel):
    """Schema for updating an existing persona."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None)
    avatar_url: Optional[str] = Field(None)
    email: Optional[EmailStr] = Field(None)

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

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_is_none(cls, v):
        """A cleared email field arrives as "" and means no address, not an
        invalid one."""
        return None if isinstance(v, str) and not v.strip() else v


class PersonaResponse(BaseModel):
    """Schema for persona API responses."""

    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str]
    avatar_url: Optional[str]
    # Which of the four sources the picture came from: "custom" when a person
    # set it, "page" when the site published it, "gravatar" when it was derived
    # from an address, "generated" when nothing was found and initials were
    # drawn. A reader deciding whether to trust a face needs to know which.
    avatar_source: Optional[str] = None
    email: Optional[str] = None
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

    model_config = ConfigDict(from_attributes=True)
