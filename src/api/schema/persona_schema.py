import re
import unicodedata
from typing import List, Optional
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.utils.input_safety import find_markup

# ---------------------------------------------------------------------------
# Field-level validation for manually created/edited personas.
#
# Only PersonaCreate and PersonaUpdate are held to these rules.
# PersonaExtract and PersonaAnalysis carry what a crawl found on someone
# else's website and must not be rejected for content we didn't write.
# ---------------------------------------------------------------------------

# (min_length, max_length) per field — 0 means no minimum enforced.
PERSONA_FIELD_LIMITS = {
    "name": (3, 50),
    "full_name": (3, 60),
    "professional_title": (3, 70),
    "description": (0, 200),
    "bio": (0, 1000),
    "demographics": (0, 300),
    "tone_of_voice": (0, 100),
    "areas_of_expertise": (0, 300),
    "goals": (0, 500),
    "pain_points": (0, 500),
    "behaviors": (0, 500),
}

# Comma-separated list limits: (max_entries, min_item_len, max_item_len).
# An entry may be a single letter, but must never be numbers or punctuation alone.
PERSONA_LIST_LIMITS = {
    "areas_of_expertise": (20, 0, 50),
    "tone_of_voice": (10, 0, 30),
    "goals": (20, 0, 120),
    "pain_points": (20, 0, 120),
    "behaviors": (20, 0, 120),
}

# --- Character sets for restricted fields ---
# Persona display name and full name: Unicode letters, spaces, apostrophes,
# hyphens, and periods only. Every other persona field accepts any character
# except HTML/script.
_UNICODE_LETTER = r"[^\W\d_]"
_DISPLAY_NAME_ALLOWED = re.compile(rf"^{_UNICODE_LETTER}+(?:[ .’'-]+{_UNICODE_LETTER}+)*$")
_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF]")
# URL validation
_LINKEDIN_RE = re.compile(
    r"^https?://([a-z]{2,3}\.)?linkedin\.com/in/[\w\-]+/?(\?.*)?$",
    re.IGNORECASE | re.UNICODE,
)


def _is_valid_http_url(value: str) -> bool:
    """Whether a string is a valid HTTP/HTTPS URL."""
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    try:
        host = parsed.hostname
    except ValueError:
        return False
    if not host:
        return False
    return True


def _validate_name_field(
    value: Optional[str], field_name: str, label: str, required: bool = False
) -> Optional[str]:
    """Validate the Persona display name or full name.

    A required field that is only whitespace is rejected rather than turned
    into None, which the NOT NULL column would refuse with a 500.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        if required:
            raise ValueError(f"{label} is required")
        return None

    min_len, max_len = PERSONA_FIELD_LIMITS[field_name]
    if min_len and len(text) < min_len:
        raise ValueError(f"{label} must be at least {min_len} characters")
    if len(text) > max_len:
        raise ValueError(f"{label} must be {max_len} characters or fewer")
    text = unicodedata.normalize("NFC", " ".join(text.split()))
    if not _DISPLAY_NAME_ALLOWED.fullmatch(text):
        raise ValueError(
            f"{label} may only contain letters, spaces, apostrophes, hyphens and periods"
        )
    if not any(char.isalpha() for char in text):
        raise ValueError(f"{label} must contain at least one letter")
    return text


def _reject_markup(text: str, label: str) -> None:
    """Reject markup and emoji from persona text fields."""
    message = find_markup(text, label)
    if message:
        raise ValueError(message)
    if _EMOJI_RE.search(text):
        raise ValueError(f"{label} cannot contain emoji")


def _require_letter(text: str, label: str) -> None:
    if not any(char.isalpha() for char in text):
        raise ValueError(f"{label} must contain at least one letter")


def _validate_title_field(value: Optional[str]) -> Optional[str]:
    """Validate professional title: optional, 3-80 chars if provided."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    _reject_markup(text, "Professional title")

    _require_letter(text, "Professional title")
    min_len, max_len = PERSONA_FIELD_LIMITS["professional_title"]
    if len(text) < min_len:
        raise ValueError(f"Professional title must be at least {min_len} characters")
    if len(text) > max_len:
        raise ValueError(f"Professional title must be {max_len} characters or fewer")
    return text


def _validate_free_text(
    value: Optional[str], field_name: str, label: str, require_letter: bool = True
) -> Optional[str]:
    """Validate a free-text field: max length, and no HTML or script."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    _reject_markup(text, label)
    if require_letter:
        _require_letter(text, label)

    _, max_len = PERSONA_FIELD_LIMITS[field_name]
    if len(text) > max_len:
        raise ValueError(f"{label} must be {max_len} characters or fewer")
    return text


def _validate_comma_list(value, field_name: str, label: str, require_letter: bool = True):
    """Validate a comma-separated field (as list or string).

    Items are free text; the strict_words argument is retained for compatibility
    with existing callers.
    """
    if value is None:
        return value

    items = (
        [str(v).strip() for v in value]
        if isinstance(value, (list, tuple))
        else [s.strip() for s in str(value).split(",")]
    )
    items = [i for i in items if i]
    if not items:
        return [] if isinstance(value, (list, tuple)) else value

    _, max_total = PERSONA_FIELD_LIMITS[field_name]
    max_items, item_min, item_max = PERSONA_LIST_LIMITS[field_name]

    joined = ", ".join(items)
    if len(joined) > max_total:
        raise ValueError(f"{label} must be {max_total} characters or fewer in total")
    if len(items) > max_items:
        raise ValueError(f"{label} may have at most {max_items} entries")

    for item in items:
        _reject_markup(item, label)
        if require_letter:
            _require_letter(item, label)
        if item_min and len(item) < item_min:
            raise ValueError(
                f'"{item}" is too short — each entry in {label} needs at least {item_min} characters'
            )
        if len(item) > item_max:
            raise ValueError(f"Each entry in {label} must be {item_max} characters or fewer")

    return items if isinstance(value, (list, tuple)) else ", ".join(items)


def _validate_avatar_url(value: Optional[str]) -> Optional[str]:
    """Validate avatar URL — accepts http(s) URLs, data URIs, and object storage keys."""
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    # Data URIs (generated initials) pass through
    if url.startswith("data:image/"):
        return url
    # HTTP(S) URLs must be valid
    if url.startswith(("http://", "https://")):
        if not _is_valid_http_url(url):
            raise ValueError("Enter a valid image URL, e.g. https://example.com/photo.jpg")
        return url
    # Object storage keys (uploaded files like "avatars/personas/<id>/avatar.png")
    if "/" in url and not url.startswith(("javascript:", "ftp:", "file:")):
        return url
    raise ValueError("Enter a valid image URL, e.g. https://example.com/photo.jpg")


def _validate_linkedin_url(value: Optional[str]) -> Optional[str]:
    """Validate LinkedIn profile URL format."""
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    if not _is_valid_http_url(url) or not _LINKEDIN_RE.match(url):
        raise ValueError(
            "Enter a valid LinkedIn profile URL, e.g. https://linkedin.com/in/username"
        )
    return url


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

    name: str = Field(
        ...,
        min_length=PERSONA_FIELD_LIMITS["name"][0],
        max_length=PERSONA_FIELD_LIMITS["name"][1],
        description="Persona display name",
    )
    description: Optional[str] = Field(
        None, max_length=PERSONA_FIELD_LIMITS["description"][1], description="Brief description"
    )
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
    full_name: Optional[str] = Field(None, max_length=PERSONA_FIELD_LIMITS["full_name"][1])
    professional_title: Optional[str] = Field(
        None, max_length=PERSONA_FIELD_LIMITS["professional_title"][1]
    )
    areas_of_expertise: Optional[List[str]] = Field(default_factory=list)
    tone_of_voice: Optional[str] = Field(None, max_length=PERSONA_FIELD_LIMITS["tone_of_voice"][1])
    bio: Optional[str] = Field(None, max_length=PERSONA_FIELD_LIMITS["bio"][1])
    linkedin_url: Optional[str] = Field(None, max_length=500)

    # User persona fields
    demographics: Optional[str] = Field(None, max_length=PERSONA_FIELD_LIMITS["demographics"][1])
    pain_points: Optional[List[str]] = Field(default_factory=list)
    goals: Optional[List[str]] = Field(default_factory=list)
    behaviors: Optional[List[str]] = Field(default_factory=list)

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_is_none(cls, v):
        """A cleared email field arrives as "" and means no address, not an
        invalid one."""
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("name")
    @classmethod
    def _check_name(cls, v):
        return _validate_name_field(v, "name", "Persona display name", required=True)

    @field_validator("full_name")
    @classmethod
    def _check_full_name(cls, v):
        return _validate_name_field(v, "full_name", "Persona full name")

    @field_validator("professional_title")
    @classmethod
    def _check_professional_title(cls, v):
        return _validate_title_field(v)

    @field_validator("description")
    @classmethod
    def _check_description(cls, v):
        return _validate_free_text(v, "description", "Short description")

    @field_validator("bio")
    @classmethod
    def _check_bio(cls, v):
        return _validate_free_text(v, "bio", "Bio", require_letter=False)

    @field_validator("demographics")
    @classmethod
    def _check_demographics(cls, v):
        return _validate_free_text(v, "demographics", "Demographics", require_letter=False)

    @field_validator("areas_of_expertise")
    @classmethod
    def _check_areas(cls, v):
        return _validate_comma_list(v, "areas_of_expertise", "Areas of expertise")

    @field_validator("tone_of_voice")
    @classmethod
    def _check_tone(cls, v):
        return _validate_comma_list(v, "tone_of_voice", "Tone of voice")

    @field_validator("goals")
    @classmethod
    def _check_goals(cls, v):
        return _validate_comma_list(v, "goals", "Goals")

    @field_validator("pain_points")
    @classmethod
    def _check_pain_points(cls, v):
        return _validate_comma_list(v, "pain_points", "Pain points", require_letter=False)

    @field_validator("behaviors")
    @classmethod
    def _check_behaviors(cls, v):
        return _validate_comma_list(v, "behaviors", "Behaviors", require_letter=False)

    @field_validator("avatar_url")
    @classmethod
    def _check_avatar(cls, v):
        return _validate_avatar_url(v)

    @field_validator("linkedin_url")
    @classmethod
    def _check_linkedin(cls, v):
        return _validate_linkedin_url(v)


class PersonaUpdate(BaseModel):
    """Schema for updating an existing persona.

    Same validation rules as PersonaCreate. Fields that are left unset are
    not touched.
    """

    name: Optional[str] = Field(
        None,
        min_length=PERSONA_FIELD_LIMITS["name"][0],
        max_length=PERSONA_FIELD_LIMITS["name"][1],
    )
    description: Optional[str] = Field(None, max_length=PERSONA_FIELD_LIMITS["description"][1])
    avatar_url: Optional[str] = Field(None)
    email: Optional[EmailStr] = Field(None)

    # E-E-A-T fields
    full_name: Optional[str] = Field(None, max_length=PERSONA_FIELD_LIMITS["full_name"][1])
    professional_title: Optional[str] = Field(
        None, max_length=PERSONA_FIELD_LIMITS["professional_title"][1]
    )
    areas_of_expertise: Optional[List[str]] = Field(None)
    tone_of_voice: Optional[str] = Field(None, max_length=PERSONA_FIELD_LIMITS["tone_of_voice"][1])
    bio: Optional[str] = Field(None, max_length=PERSONA_FIELD_LIMITS["bio"][1])
    linkedin_url: Optional[str] = Field(None, max_length=500)

    # User persona fields
    demographics: Optional[str] = Field(None, max_length=PERSONA_FIELD_LIMITS["demographics"][1])
    pain_points: Optional[List[str]] = Field(None)
    goals: Optional[List[str]] = Field(None)
    behaviors: Optional[List[str]] = Field(None)

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email_is_none(cls, v):
        """A cleared email field arrives as "" and means no address, not an
        invalid one."""
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("name")
    @classmethod
    def _check_name(cls, v):
        return _validate_name_field(v, "name", "Persona display name", required=True)

    @field_validator("full_name")
    @classmethod
    def _check_full_name(cls, v):
        return _validate_name_field(v, "full_name", "Persona full name")

    @field_validator("professional_title")
    @classmethod
    def _check_professional_title(cls, v):
        return _validate_title_field(v)

    @field_validator("description")
    @classmethod
    def _check_description(cls, v):
        return _validate_free_text(v, "description", "Short description")

    @field_validator("bio")
    @classmethod
    def _check_bio(cls, v):
        return _validate_free_text(v, "bio", "Bio", require_letter=False)

    @field_validator("demographics")
    @classmethod
    def _check_demographics(cls, v):
        return _validate_free_text(v, "demographics", "Demographics", require_letter=False)

    @field_validator("areas_of_expertise")
    @classmethod
    def _check_areas(cls, v):
        return _validate_comma_list(v, "areas_of_expertise", "Areas of expertise")

    @field_validator("tone_of_voice")
    @classmethod
    def _check_tone(cls, v):
        return _validate_comma_list(v, "tone_of_voice", "Tone of voice")

    @field_validator("goals")
    @classmethod
    def _check_goals(cls, v):
        return _validate_comma_list(v, "goals", "Goals")

    @field_validator("pain_points")
    @classmethod
    def _check_pain_points(cls, v):
        return _validate_comma_list(v, "pain_points", "Pain points", require_letter=False)

    @field_validator("behaviors")
    @classmethod
    def _check_behaviors(cls, v):
        return _validate_comma_list(v, "behaviors", "Behaviors", require_letter=False)

    @field_validator("avatar_url")
    @classmethod
    def _check_avatar(cls, v):
        return _validate_avatar_url(v)

    @field_validator("linkedin_url")
    @classmethod
    def _check_linkedin(cls, v):
        return _validate_linkedin_url(v)


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
