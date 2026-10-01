import re
import unicodedata
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    constr,
    field_validator,
    model_validator,
)

from src.api.schema.persona_schema import PersonaExtract
from src.utils.input_safety import find_markup


# -------------------------------------
# Knowledge Base Schema
# -------------------------------------
class KnowledgeBaseCreateSchema(BaseModel):
    """Schema for creating a knowledge base"""

    name: constr(min_length=1, max_length=255) = Field(
        ..., description="Name of the knowledge base", example="Product Documentation"
    )
    description: Optional[str] = Field(
        None,
        description="Optional description of the knowledge base",
        example="Contains all product-related documentation and guides",
    )


class KnowledgeBaseUpdateSchema(BaseModel):
    """Schema for updating a knowledge base"""

    name: Optional[constr(min_length=1, max_length=255)] = Field(
        None, description="Name of the knowledge base", example="Updated Product Documentation"
    )
    description: Optional[str] = Field(
        None, description="Description of the knowledge base", example="Updated description"
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

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------
# Brand Voice Schema
# -------------------------------------
BRAND_TEXT_MAX_LENGTH = {
    "brand_name": 255,
    "about": 2000,
    "customer_profile": 2000,
    "selling_position": 2000,
}
BRAND_LIST_MAX_ITEMS = 50
BRAND_LIST_ITEM_MAX_LENGTH = 255
_BRAND_LABELS = {
    "brand_name": "Brand name",
    "about": "About",
    "customer_profile": "Customer profile",
    "selling_position": "Selling position",
    "target_audience": "Target audience",
    "brand_voice": "Brand voice",
    "competitors": "Competitors",
    "content_pillar": "Content pillars",
}

# A web address in any form: a scheme, "www.", or a word glued to a domain
# ending such as "nike.com" or "acme.co.uk". "Dr. Martens" has a space after
# the dot, so it is still a name.
_URL_LIKE_RE = re.compile(r"https?:|://|\bwww\.|[a-z0-9-]\.[a-z]{2,}\b", re.IGNORECASE)
# Placeholder and test values that are never a real company.
_DUMMY_COMPETITOR_RE = re.compile(
    r"^(?:test(?:ing)?|dummy|sample|example|demo|fake|temp|placeholder|lorem(?: ipsum)?"
    r"|foo|bar|foobar|baz|abc|abcd|abcde|xyz|xxx+|asdf\w*|qwerty\w*|none|nil|null|na|n a"
    r"|unknown|tbd|todo|hello|hi|ok|random|anything|something|nothing|no competitors?"
    r"|(?:my |our |a |the )?(?:competitor|company|brand|business|name)"
    r")(?: ?\d+)?$",
    re.IGNORECASE,
)
_KEYBOARD_RUN_RE = re.compile(
    r"qwert|werty|asdf|sdfg|dfgh|fghj|ghjk|hjkl|zxcv|xcvb|cvbn|vbnm", re.I
)
_TRIPLE_CHAR_RE = re.compile(r"(\w)\1\1", re.IGNORECASE)
_VOWEL_RE = re.compile(r"[aeiouy]", re.IGNORECASE)


def _is_emoji(char: str) -> bool:
    code = ord(char)
    return (
        0x1F000 <= code <= 0x1FAFF  # pictographs, emoticons, flags
        or 0x2600 <= code <= 0x27BF  # misc symbols and dingbats (☀ ✈ ❤)
        or unicodedata.category(char) in {"Cs", "Co"}
    )


def _brand_text_problem(value: str, label: str) -> str | None:
    """Why a brand voice text value is not acceptable, or None when it is."""
    message = find_markup(value, label)
    if message:
        return message
    # Symbols such as ™ © ® & % $ # @ are fine; only emoji are refused.
    if any(_is_emoji(char) for char in value):
        return f"{label} cannot contain emojis"
    # Rejects values made only of numbers, only of punctuation, or both.
    if not any(char.isalpha() for char in value):
        return f"{label} must contain letters, not only numbers or special characters"
    return None


def competitor_name_problem(name: str) -> str | None:
    """Why `name` is not a believable competitor name, or None when it is.

    Only the shape of the name can be checked here, not whether the company
    really exists: a URL or domain, a placeholder ("test", "competitor 1"),
    keyboard mashing ("asdfgh", "xkcdqz") and repeated letters ("aaaa") are
    rejected.
    """
    if _URL_LIKE_RE.search(name):
        return (
            f'"{name}" looks like a website. Enter the competitor\'s name, e.g. "Nike", not a URL'
        )
    letters = "".join(char for char in name if char.isalpha())
    if len(letters) < 2:
        return f'"{name}" is not a valid competitor name'
    simplified = " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())
    if _DUMMY_COMPETITOR_RE.match(simplified):
        return f'"{name}" is a placeholder, not a real competitor name'
    if _KEYBOARD_RUN_RE.search(letters) or _TRIPLE_CHAR_RE.search(name):
        return f'"{name}" does not look like a real competitor name'
    for word in re.findall(r"[A-Za-z]+", name):
        # Acronyms such as "HSBC" or "KPMG" have no vowels but are all capitals.
        if len(word) >= 5 and not word.isupper() and not _VOWEL_RE.search(word):
            return f'"{name}" does not look like a real competitor name'
    return None


def _drop_invalid_competitors(value):
    """AI extraction keeps only the competitors that pass the name checks."""
    if not isinstance(value, list):
        return value
    return [
        item
        for item in value
        if isinstance(item, str) and item.strip() and not competitor_name_problem(item.strip())
    ]


class BrandSchema(BaseModel):
    """Brand voice as extracted by the AI pipeline and returned to clients.

    Kept lenient so one odd model answer does not fail extraction; user edits
    go through BrandVoiceUpdateSchema, which enforces every rule.
    """

    brand_name: str | None = Field(
        default=None,
        max_length=255,
        description="The brand/product's actual name — used verbatim in generated content, never inferred from the workspace name",
        example="Everlane",
    )
    about: str | None = Field(
        default=None,
        description="Brief description about the brand",
        example="We are a sustainable fashion brand focusing on eco-friendly clothing.",
    )
    customer_profile: str | None = Field(
        default=None,
        description="Details about target customers",
        example="Environmentally conscious millennials and Gen Z.",
    )
    selling_position: str | None = Field(
        default=None,
        description="Unique selling proposition of the brand",
        example="Affordable eco-friendly fashion for young adults.",
    )
    target_audience: List[str] = Field(
        default_factory=list,
        description="List of target audience segments",
        example=["Students", "Young Professionals", "Eco-conscious Consumers"],
    )
    brand_voice: List[str] = Field(
        default_factory=list,
        description="Tone and style of communication",
        example=["Friendly", "Inspirational", "Authentic"],
    )
    competitors: List[str] = Field(
        default_factory=list,
        description="Real, named market competitors (brand/company names only, not URLs, partners, or clients)",
        example=["Patagonia", "Everlane"],
    )
    content_pillar: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("content_pillar", "content_strategy"),
        description="Main content pillars or strategy themes",
        example=["Sustainability", "Fashion Trends", "Eco-lifestyle"],
    )

    _clean_competitors = field_validator("competitors")(_drop_invalid_competitors)

    model_config = ConfigDict(populate_by_name=True)

    personas: List[PersonaExtract] = Field(
        default_factory=list,
        description="Author/Expert personas - REAL PEOPLE from the website (founders, authors, team members, experts). NOT customer personas.",
        example=[
            {
                "name": "Mobheen Abdullah",
                "description": "Founder & CEO specializing in sustainable fashion",
                "full_name": "Mobheen Abdullah",
                "professional_title": "Founder & Chief Executive Officer",
                "areas_of_expertise": "Sustainable Fashion, E-commerce, Brand Strategy",
                "tone_of_voice": "Passionate, Authentic, Educational",
                "bio": "Mobheen Abdullah founded the company in 2020 with a mission to make sustainable fashion accessible...",
                "linkedin_url": "https://linkedin.com/in/mobheenabdullah",
            }
        ],
    )


class BrandVoiceUpdateSchema(BrandSchema):
    """Brand voice as edited by a user: every field is validated, nothing is
    silently dropped.

    - Text: trimmed, within its length limit, contains letters (not only
      numbers or special characters), no HTML/script, emoji or hidden characters.
    - Lists: at most 50 unique entries, each following the text rules.
    - Competitors: not the brand itself. Ones the user adds must also be a
      company name (not a URL, domain, placeholder or keyboard mashing) with a
      live site; that is checked in BrandVoiceService so saved ones are kept.
    """

    @field_validator("brand_name", "about", "customer_profile", "selling_position", mode="before")
    @classmethod
    def _check_text(cls, value, info):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("must be text")
        label = _BRAND_LABELS[info.field_name]
        text = " ".join(value.split())
        if not text:
            # A cleared field is stored as empty, not rejected.
            return None
        max_length = BRAND_TEXT_MAX_LENGTH[info.field_name]
        if len(text) > max_length:
            raise ValueError(f"{label} must be {max_length} characters or fewer")
        problem = _brand_text_problem(text, label)
        if problem:
            raise ValueError(problem)
        return text

    @field_validator(
        "target_audience", "brand_voice", "competitors", "content_pillar", mode="before"
    )
    @classmethod
    def _check_list(cls, value, info):
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("must be a list")
        label = _BRAND_LABELS[info.field_name]
        items = []
        seen = set()
        for raw in value:
            if not isinstance(raw, str):
                raise ValueError(f"Each entry in {label} must be text")
            item = " ".join(raw.split())
            if not item:
                continue
            if len(item) > BRAND_LIST_ITEM_MAX_LENGTH:
                raise ValueError(
                    f"Each entry in {label} must be {BRAND_LIST_ITEM_MAX_LENGTH} characters or fewer"
                )
            # Competitor name rules are applied by BrandVoiceService to the
            # ones the user adds, so saved AI-extracted competitors (stored as
            # domains) never block a save.
            problem = _brand_text_problem(item, f'"{item}" in {label}')
            if problem:
                raise ValueError(problem)
            if item.casefold() in seen:
                raise ValueError(f'"{item}" is listed more than once in {label}')
            seen.add(item.casefold())
            items.append(item)
        if len(items) > BRAND_LIST_MAX_ITEMS:
            raise ValueError(f"{label} may have at most {BRAND_LIST_MAX_ITEMS} entries")
        return items

    @field_validator("competitors")
    @classmethod
    def _clean_competitors(cls, value):
        """Overrides BrandSchema's AI-extraction filter: a user's save never
        silently drops a competitor."""
        return value

    @model_validator(mode="after")
    def _competitor_is_not_the_brand(self):
        brand = (self.brand_name or "").casefold()
        if brand and any(item.casefold() == brand for item in self.competitors):
            raise ValueError("Your own brand cannot be listed as a competitor")
        return self


class CompetitorValidationRequest(BaseModel):
    """A single competitor name validated before the UI adds its chip."""

    competitor: str

    @field_validator("competitor")
    @classmethod
    def _check_competitor(cls, value: str) -> str:
        competitor = BrandVoiceUpdateSchema(competitors=[value]).competitors[0]
        problem = competitor_name_problem(competitor)
        if problem:
            raise ValueError(problem)
        return competitor


# -------------------------------------
# -------------------------------------
# Text Knowledge Schema
# -------------------------------------
class TextKnowledgeSchema(BaseModel):
    content: constr(min_length=10, max_length=5000) = Field(
        ...,
        description="Text content to store as knowledge",
        example="AI can help automate customer service, improve personalization, and optimize marketing strategies.",
    )
    workspace_id: UUID = Field(
        ..., description="Workspace identifier", example="123e4567-e89b-12d3-a456-426614174000"
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

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------
# Web Knowledge Schema
# -------------------------------------
class WebKnowledgeSchema(BaseModel):
    url: HttpUrl = Field(
        ...,
        description="Add a URL you want to include in your knowledge",
        example="https://example.com",
    )
    workspace_id: UUID = Field(
        ..., description="Workspace identifier", example="123e4567-e89b-12d3-a456-426614174000"
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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)
