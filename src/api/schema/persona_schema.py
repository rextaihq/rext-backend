import re
from typing import List, Optional
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Field rules for personas a person types in.
#
# These mirror `lib/validation/persona-validation.ts` in the admin app. The
# frontend copy exists to say what is wrong while someone is still typing; this
# one is the rule, because the endpoint is reachable without it — every bad
# value the test plan found (a malformed avatar URL, unbounded prose, markup in
# a bio) arrived through a form that had simply not checked.
#
# Only the manual-entry schemas below are held to them. `PersonaExtract` and
# `PersonaAnalysis` carry what a crawl found on somebody else's website, and
# rejecting a real person's bio because their site writes it with a character
# we disallow in our own form would lose the extraction, not improve it.
# ---------------------------------------------------------------------------

#: Lengths in characters, keyed by field. Kept beside the schema so a limit is
#: changed in one place rather than in each validator that happens to use it.
PERSONA_FIELD_LIMITS = {
    "name": (2, 60),
    "full_name": (2, 100),
    # Per the meeting decision: optional, and deliberately short.
    "professional_title": (4, 14),
    "description": (0, 200),
    "bio": (10, 1000),
    "demographics": (0, 300),
    "tone_of_voice": (0, 100),
    "areas_of_expertise": (0, 300),
    "goals": (0, 500),
    "pain_points": (0, 500),
    "behaviors": (0, 500),
}

#: Comma-separated fields: how many entries, and how long each may be.
PERSONA_LIST_LIMITS = {
    "areas_of_expertise": (20, 2, 50),
    "goals": (20, 2, 120),
    "pain_points": (20, 2, 120),
    "behaviors": (20, 2, 120),
}

_CONTAINS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
#: Markup, template and shell furniture. None of it belongs in a bio, and all
#: of it is what turns a stored field into a rendering problem later.
_UNSAFE_TEXT_CHARS = re.compile(r"[<>{}\[\]\\|`~^$*=+_#@]")
#: Tabs and newlines are fine in a textarea; the rest of C0 and DEL are not.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def _name_charset_ok(value: str) -> bool:
    """Whether every character is one that belongs in a name or a title."""
    allowed_punctuation = set(" .,'’&()-/")
    return all(ch.isalnum() or ch in allowed_punctuation for ch in value)


def _check_text(
    value: Optional[str],
    field: str,
    label: str,
    *,
    names: bool = False,
    require_letter: bool = False,
) -> Optional[str]:
    """One field against its rules. Raises `ValueError`, which Pydantic turns
    into the 422 the form displays; returns the trimmed value otherwise."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    minimum, maximum = PERSONA_FIELD_LIMITS[field]
    if _CONTROL_CHARS.search(text):
        raise ValueError(f"{label} contains characters that are not allowed")
    if minimum and len(text) < minimum:
        raise ValueError(f"{label} must be at least {minimum} characters")
    if maximum and len(text) > maximum:
        raise ValueError(f"{label} must be {maximum} characters or fewer")
    if require_letter and not _CONTAINS_LETTER.search(text):
        raise ValueError(f"{label} must contain at least one letter")
    if names:
        if not _name_charset_ok(text):
            raise ValueError(f"{label} may only contain letters, numbers, spaces and . , ' - & ( )")
    else:
        bad = sorted(set(_UNSAFE_TEXT_CHARS.findall(text)))
        if bad:
            raise ValueError(f"{label} cannot contain {' '.join(bad)}")
    return text


def _check_list(value, field: str, label: str):
    """A comma-separated field, as a list or as one string."""
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

    _, max_total = PERSONA_FIELD_LIMITS[field]
    max_items, item_min, item_max = PERSONA_LIST_LIMITS[field]
    joined = ", ".join(items)
    if _CONTROL_CHARS.search(joined):
        raise ValueError(f"{label} contains characters that are not allowed")
    bad = sorted(set(_UNSAFE_TEXT_CHARS.findall(joined)))
    if bad:
        raise ValueError(f"{label} cannot contain {' '.join(bad)}")
    if len(joined) > max_total:
        raise ValueError(f"{label} must be {max_total} characters or fewer")
    if len(items) > max_items:
        raise ValueError(f"{label} may list at most {max_items} entries")
    for item in items:
        if len(item) < item_min:
            raise ValueError(f"Each entry in {label} must be at least {item_min} characters")
        if len(item) > item_max:
            raise ValueError(f"Each entry in {label} must be {item_max} characters or fewer")
        if not _CONTAINS_LETTER.search(item):
            raise ValueError(f"Each entry in {label} must contain at least one letter")
    return items


def is_valid_http_url(value: str) -> bool:
    """Whether a string is a URL a browser could actually fetch.

    Parsing alone is not enough. "https:///example.com" has no host,
    "https://-example.com" has a label that cannot begin with a hyphen, and
    "https://example,com" has a character that is not a host character — all
    three parse, none of them resolve, and all three were being stored.
    """
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
    if host == "localhost":
        return True
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        return all(int(octet) <= 255 for octet in host.split("."))

    labels = host.split(".")
    if len(labels) < 2:
        return False
    label_re = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?")
    if not all(len(part) <= 63 and label_re.fullmatch(part) for part in labels):
        return False
    return bool(re.fullmatch(r"[a-zA-Z]{2,}", labels[-1]))


_LINKEDIN_RE = re.compile(
    r"^https?://([a-z]{2,3}\.)?linkedin\.com/in/[\w\-]+/?$", re.IGNORECASE | re.UNICODE
)


#: A stored object key: "avatars/personas/<id>/avatar_1.png". Relative, made
#: only of the characters the upload route builds keys from, and containing at
#: least one slash — without that, a bare typed word would be waved through as
#: though it were a key.
_OBJECT_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)+")
_HAS_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:")


def _check_avatar_url(value: Optional[str]) -> Optional[str]:
    """Rejects the malformed links that were being accepted.

    A stored object key (an uploaded file) and a data URI (generated initials)
    are ours rather than something a person typed, so they pass through — but
    only after being recognised as such. Letting anything without an http
    prefix through, which is what "not a URL, so it must be a key" amounted to,
    also let "javascript:alert(1)" into a field that ends up in an img src.
    """
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    if len(url) > 500 and not url.startswith("data:"):
        raise ValueError("Avatar URL must be 500 characters or fewer")
    if url.startswith("data:image/"):
        return url
    if url.startswith(("http://", "https://")):
        if not is_valid_http_url(url):
            raise ValueError("Enter a valid image URL, e.g. https://example.com/photo.jpg")
        return url
    # Anything else carrying a scheme is not a key and not a link we serve.
    if _HAS_SCHEME_RE.match(url) or not _OBJECT_KEY_RE.fullmatch(url):
        raise ValueError("Enter a valid image URL, e.g. https://example.com/photo.jpg")
    return url


def _check_linkedin_url(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    if not is_valid_http_url(url) or not _LINKEDIN_RE.match(url):
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
        description="Persona display name. Required, and never filled in from full_name.",
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
    #: Optional per the meeting decision — it used to be required by the form.
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
        return _check_text(v, "name", "Persona display name", names=True, require_letter=True)

    @field_validator("full_name")
    @classmethod
    def _check_full_name(cls, v):
        return _check_text(v, "full_name", "Persona full name", names=True, require_letter=True)

    @field_validator("professional_title")
    @classmethod
    def _check_professional_title(cls, v):
        return _check_text(
            v, "professional_title", "Professional title", names=True, require_letter=True
        )

    @field_validator("description")
    @classmethod
    def _check_description(cls, v):
        return _check_text(v, "description", "Short description")

    @field_validator("bio")
    @classmethod
    def _check_bio(cls, v):
        return _check_text(v, "bio", "Bio")

    @field_validator("demographics")
    @classmethod
    def _check_demographics(cls, v):
        return _check_text(v, "demographics", "Demographics")

    @field_validator("tone_of_voice")
    @classmethod
    def _check_tone(cls, v):
        return _check_text(v, "tone_of_voice", "Tone of voice")

    @field_validator("areas_of_expertise")
    @classmethod
    def _check_areas(cls, v):
        return _check_list(v, "areas_of_expertise", "Areas of expertise")

    @field_validator("goals")
    @classmethod
    def _check_goals(cls, v):
        return _check_list(v, "goals", "Goals")

    @field_validator("pain_points")
    @classmethod
    def _check_pain_points(cls, v):
        return _check_list(v, "pain_points", "Pain points")

    @field_validator("behaviors")
    @classmethod
    def _check_behaviors(cls, v):
        return _check_list(v, "behaviors", "Behaviors")

    @field_validator("avatar_url")
    @classmethod
    def _check_avatar(cls, v):
        return _check_avatar_url(v)

    @field_validator("linkedin_url")
    @classmethod
    def _check_linkedin(cls, v):
        return _check_linkedin_url(v)


class PersonaUpdate(BaseModel):
    """Schema for updating an existing persona.

    Held to the same rules as `PersonaCreate`. The edit form sends every field
    back on each save, so a persona that predates these limits — one the
    crawler extracted, say — is checked the moment somebody edits it. Fields
    that are left unset are not touched.
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
        return _check_text(v, "name", "Persona display name", names=True, require_letter=True)

    @field_validator("full_name")
    @classmethod
    def _check_full_name(cls, v):
        return _check_text(v, "full_name", "Persona full name", names=True, require_letter=True)

    @field_validator("professional_title")
    @classmethod
    def _check_professional_title(cls, v):
        return _check_text(
            v, "professional_title", "Professional title", names=True, require_letter=True
        )

    @field_validator("description")
    @classmethod
    def _check_description(cls, v):
        return _check_text(v, "description", "Short description")

    @field_validator("bio")
    @classmethod
    def _check_bio(cls, v):
        return _check_text(v, "bio", "Bio")

    @field_validator("demographics")
    @classmethod
    def _check_demographics(cls, v):
        return _check_text(v, "demographics", "Demographics")

    @field_validator("tone_of_voice")
    @classmethod
    def _check_tone(cls, v):
        return _check_text(v, "tone_of_voice", "Tone of voice")

    @field_validator("areas_of_expertise")
    @classmethod
    def _check_areas(cls, v):
        return _check_list(v, "areas_of_expertise", "Areas of expertise")

    @field_validator("goals")
    @classmethod
    def _check_goals(cls, v):
        return _check_list(v, "goals", "Goals")

    @field_validator("pain_points")
    @classmethod
    def _check_pain_points(cls, v):
        return _check_list(v, "pain_points", "Pain points")

    @field_validator("behaviors")
    @classmethod
    def _check_behaviors(cls, v):
        return _check_list(v, "behaviors", "Behaviors")

    @field_validator("avatar_url")
    @classmethod
    def _check_avatar(cls, v):
        return _check_avatar_url(v)

    @field_validator("linkedin_url")
    @classmethod
    def _check_linkedin(cls, v):
        return _check_linkedin_url(v)


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
