"""Industry and topic color palettes."""

from __future__ import annotations

from dataclasses import dataclass

from src.flow.image_generation.models import BrandStyle, ColorPalette, Industry


@dataclass(frozen=True)
class PaletteDefinition:
    """Named palette used by the Art Director."""

    industry: Industry
    name: str
    primary: str
    secondary: str
    accent: str
    background: str
    harmony: str
    keywords: tuple[str, ...]


PALETTE_DEFINITIONS: tuple[PaletteDefinition, ...] = (
    PaletteDefinition(
        industry=Industry.TECHNOLOGY,
        name="Technology",
        primary="blue",
        secondary="cyan",
        accent="purple",
        background="dark navy",
        harmony="analogous with restrained complementary accent",
        keywords=("tech", "software", "saas", "ai", "cloud", "digital", "platform", "api"),
    ),
    PaletteDefinition(
        industry=Industry.HEALTHCARE,
        name="Healthcare",
        primary="white",
        secondary="soft teal",
        accent="blue",
        background="clean light gray",
        harmony="cool clinical calm",
        keywords=("health", "healthcare", "medical", "patient", "clinic", "wellness"),
    ),
    PaletteDefinition(
        industry=Industry.MEDICAL,
        name="Medical",
        primary="white",
        secondary="soft teal",
        accent="blue",
        background="sterile light gray",
        harmony="cool clinical calm",
        keywords=("medicine", "hospital", "doctor", "pharma", "diagnosis"),
    ),
    PaletteDefinition(
        industry=Industry.EDUCATION,
        name="Education",
        primary="orange",
        secondary="blue",
        accent="warm amber",
        background="soft cream",
        harmony="warm complementary learning palette",
        keywords=("education", "learning", "course", "student", "training", "school"),
    ),
    PaletteDefinition(
        industry=Industry.FINANCE,
        name="Finance",
        primary="green",
        secondary="navy",
        accent="gold",
        background="deep navy",
        harmony="trustworthy complementary",
        keywords=("finance", "fintech", "banking", "investment", "money", "accounting"),
    ),
    PaletteDefinition(
        industry=Industry.MARKETING,
        name="Marketing",
        primary="purple",
        secondary="magenta",
        accent="pink",
        background="deep charcoal",
        harmony="vibrant analogous accents",
        keywords=("marketing", "brand", "campaign", "growth", "advertising", "content"),
    ),
    PaletteDefinition(
        industry=Industry.BUSINESS,
        name="Business",
        primary="navy",
        secondary="slate blue",
        accent="teal",
        background="soft charcoal",
        harmony="professional cool neutrals",
        keywords=("business", "enterprise", "corporate", "strategy", "operations"),
    ),
    PaletteDefinition(
        industry=Industry.FOOD,
        name="Food",
        primary="warm terracotta",
        secondary="olive",
        accent="golden yellow",
        background="warm ivory",
        harmony="appetizing warm natural tones",
        keywords=("food", "recipe", "restaurant", "culinary", "cuisine"),
    ),
    PaletteDefinition(
        industry=Industry.GENERAL,
        name="General Editorial",
        primary="blue",
        secondary="soft gray",
        accent="teal",
        background="muted charcoal",
        harmony="neutral editorial",
        keywords=(),
    ),
)


BRAND_PALETTE_OVERRIDES: dict[BrandStyle, dict[str, str]] = {
    BrandStyle.LUXURY: {
        "primary": "black",
        "secondary": "charcoal",
        "accent": "gold",
        "background": "deep black",
        "harmony": "high-contrast luxury",
    },
    BrandStyle.DEVELOPER: {
        "primary": "electric blue",
        "secondary": "cyan",
        "accent": "subtle neon green",
        "background": "near-black terminal gray",
        "harmony": "dark mode with restrained glow",
    },
    BrandStyle.STARTUP: {
        "primary": "vivid blue",
        "secondary": "coral",
        "accent": "lime",
        "background": "soft dark slate",
        "harmony": "energetic complementary accents",
    },
}


def detect_industry(
    title: str = "",
    summary: str = "",
    primary_keyword: str = "",
    secondary_keywords: list[str] | None = None,
    industry_hint: str | None = None,
) -> Industry:
    """Detect industry from topic signals."""
    if industry_hint:
        hint = industry_hint.strip().lower().replace(" ", "_")
        for industry in Industry:
            if industry.value == hint or industry.name.lower() == hint:
                return industry

    blob = " ".join(
        [
            title,
            summary,
            primary_keyword,
            " ".join(secondary_keywords or []),
        ]
    ).lower()

    best = Industry.GENERAL
    best_score = 0
    for definition in PALETTE_DEFINITIONS:
        if definition.industry == Industry.GENERAL:
            continue
        score = sum(1 for keyword in definition.keywords if keyword in blob)
        if score > best_score:
            best = definition.industry
            best_score = score
    return best


def get_palette_definition(industry: Industry) -> PaletteDefinition:
    """Return palette definition for an industry."""
    for definition in PALETTE_DEFINITIONS:
        if definition.industry == industry:
            return definition
    return PALETTE_DEFINITIONS[-1]


def resolve_color_palette(
    industry: Industry,
    brand_style: BrandStyle | None = None,
) -> ColorPalette:
    """Build a ColorPalette from industry and optional brand overrides."""
    definition = get_palette_definition(industry)
    data = {
        "name": definition.name,
        "primary": definition.primary,
        "secondary": definition.secondary,
        "accent": definition.accent,
        "background": definition.background,
        "harmony": definition.harmony,
    }
    if brand_style and brand_style in BRAND_PALETTE_OVERRIDES:
        data.update(BRAND_PALETTE_OVERRIDES[brand_style])
        data["name"] = f"{definition.name} / {brand_style.value}"
    return ColorPalette(**data)
