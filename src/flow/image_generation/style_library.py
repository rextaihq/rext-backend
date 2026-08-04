"""Reusable visual brand style definitions."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.flow.image_generation.models import BrandStyle


@dataclass(frozen=True)
class StyleProfile:
    """Reusable visual style profile."""

    key: BrandStyle
    label: str
    adjectives: tuple[str, ...]
    mood: tuple[str, ...]
    design_language: tuple[str, ...]
    preferred_rendering_hints: tuple[str, ...] = field(default_factory=tuple)
    keywords: tuple[str, ...] = field(default_factory=tuple)


STYLE_PROFILES: dict[BrandStyle, StyleProfile] = {
    BrandStyle.PREMIUM_SAAS: StyleProfile(
        key=BrandStyle.PREMIUM_SAAS,
        label="Premium SaaS",
        adjectives=(
            "clean",
            "premium",
            "editorial",
            "minimal",
            "enterprise",
            "trustworthy",
            "elegant",
            "modern",
            "spacious",
            "sophisticated",
        ),
        mood=("innovation", "trust", "scalability", "enterprise readiness"),
        design_language=("editorial", "enterprise", "restrained luxury"),
        preferred_rendering_hints=("3d editorial illustration", "soft volumetric lighting"),
        keywords=("saas", "enterprise", "platform", "cloud", "b2b", "software"),
    ),
    BrandStyle.STARTUP: StyleProfile(
        key=BrandStyle.STARTUP,
        label="Startup",
        adjectives=("energetic", "bold", "vibrant", "playful", "modern", "optimistic"),
        mood=("momentum", "creativity", "growth", "possibility"),
        design_language=("bold", "dynamic", "youthful"),
        preferred_rendering_hints=("flat illustration", "vibrant accents"),
        keywords=("startup", "founder", "growth", "mvp", "venture"),
    ),
    BrandStyle.LUXURY: StyleProfile(
        key=BrandStyle.LUXURY,
        label="Luxury",
        adjectives=("cinematic", "premium", "refined", "exclusive", "timeless"),
        mood=("prestige", "craftsmanship", "exclusivity"),
        design_language=("black and gold", "cinematic", "high contrast"),
        preferred_rendering_hints=("cinematic", "dramatic lighting"),
        keywords=("luxury", "premium", "exclusive", "high-end", "bespoke"),
    ),
    BrandStyle.DEVELOPER: StyleProfile(
        key=BrandStyle.DEVELOPER,
        label="Developer",
        adjectives=("dark", "precise", "technical", "focused", "modern"),
        mood=("clarity", "craft", "deep work", "technical confidence"),
        design_language=("terminal inspired", "subtle glow", "dark mode"),
        preferred_rendering_hints=("technical illustration", "subtle neon accents"),
        keywords=("developer", "api", "code", "engineering", "devops", "sdk"),
    ),
    BrandStyle.CORPORATE: StyleProfile(
        key=BrandStyle.CORPORATE,
        label="Corporate",
        adjectives=("polished", "reliable", "professional", "clear", "authoritative"),
        mood=("stability", "credibility", "leadership"),
        design_language=("corporate editorial", "clean geometry"),
        preferred_rendering_hints=("photorealistic", "natural light"),
        keywords=("corporate", "business", "executive", "enterprise", "boardroom"),
    ),
    BrandStyle.FRIENDLY: StyleProfile(
        key=BrandStyle.FRIENDLY,
        label="Friendly",
        adjectives=("warm", "approachable", "simple", "human", "inviting"),
        mood=("helpfulness", "ease", "reassurance"),
        design_language=("soft shapes", "friendly minimal"),
        preferred_rendering_hints=("flat illustration", "soft lighting"),
        keywords=("faq", "help", "guide", "beginner", "friendly"),
    ),
    BrandStyle.EDITORIAL: StyleProfile(
        key=BrandStyle.EDITORIAL,
        label="Editorial",
        adjectives=("journalistic", "story-driven", "credible", "contemporary"),
        mood=("insight", "authority", "narrative clarity"),
        design_language=("magazine editorial", "reportage"),
        preferred_rendering_hints=("editorial photography", "natural light"),
        keywords=("news", "report", "analysis", "journalism", "editorial"),
    ),
}


def get_style_profile(style: BrandStyle) -> StyleProfile:
    """Return a style profile, defaulting to Premium SaaS."""
    return STYLE_PROFILES.get(style, STYLE_PROFILES[BrandStyle.PREMIUM_SAAS])


def resolve_brand_style(
    brand_voice: str = "",
    writing_style: str = "",
    audience: list[str] | None = None,
    content_type: str = "",
    title: str = "",
    summary: str = "",
) -> BrandStyle:
    """Infer brand style from voice, audience, and topic signals."""
    audience = audience or []
    blob = " ".join(
        [
            brand_voice,
            writing_style,
            content_type,
            title,
            summary,
            " ".join(audience),
        ]
    ).lower()

    scores: dict[BrandStyle, int] = {style: 0 for style in BrandStyle}
    for style, profile in STYLE_PROFILES.items():
        for keyword in profile.keywords:
            if keyword in blob:
                scores[style] += 2
        for adjective in profile.adjectives:
            if adjective in blob:
                scores[style] += 1

    if any(token in blob for token in ("developer", "engineer", "api", "devops", "sdk")):
        scores[BrandStyle.DEVELOPER] += 3
    if any(token in blob for token in ("luxury", "premium", "exclusive")):
        scores[BrandStyle.LUXURY] += 3
    if any(token in blob for token in ("startup", "founder", "venture")):
        scores[BrandStyle.STARTUP] += 3
    if any(token in blob for token in ("enterprise", "saas", "b2b", "platform")):
        scores[BrandStyle.PREMIUM_SAAS] += 3
    if any(token in blob for token in ("faq", "help", "beginner", "friendly")):
        scores[BrandStyle.FRIENDLY] += 2
    if any(token in blob for token in ("news", "report", "journal")):
        scores[BrandStyle.EDITORIAL] += 2

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return BrandStyle.PREMIUM_SAAS
    return best
