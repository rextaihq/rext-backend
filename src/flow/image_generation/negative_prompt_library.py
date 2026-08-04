"""Reusable negative prompt library by domain."""

from __future__ import annotations

from dataclasses import dataclass

from src.flow.image_generation.models import Industry


@dataclass(frozen=True)
class NegativePromptSet:
    """Named set of objects / qualities to avoid."""

    name: str
    avoid: tuple[str, ...]


UNIVERSAL_AVOID: tuple[str, ...] = (
    "readable text",
    "logos",
    "watermarks",
    "signatures",
    "clutter",
    "duplicated people",
    "duplicated subjects",
    "distorted hands",
    "extra fingers",
    "cropped faces",
    "low resolution",
    "oversaturated colors",
    "blurry details",
    "jpeg artifacts",
)

DOMAIN_NEGATIVES: dict[str, NegativePromptSet] = {
    "technology": NegativePromptSet(
        name="Technology",
        avoid=(
            "infographic",
            "fake UI",
            "fake dashboard",
            "unreadable typography",
            "floating interface panels",
            "screenshot mockups",
            "stock-photo holograms",
            "matrix code rain",
        ),
    ),
    "business": NegativePromptSet(
        name="Business",
        avoid=(
            "handshake clichés",
            "random floating icons",
            "exaggerated holograms",
            "unnecessary charts",
            "pointing at screens cliché",
            "forced corporate smiles",
            "generic skyline montage",
        ),
    ),
    "medical": NegativePromptSet(
        name="Medical",
        avoid=(
            "graphic injuries",
            "horror style",
            "blood",
            "surgical gore",
            "distressing clinical imagery",
        ),
    ),
    "healthcare": NegativePromptSet(
        name="Healthcare",
        avoid=(
            "graphic injuries",
            "horror style",
            "blood",
            "distressing clinical imagery",
        ),
    ),
    "food": NegativePromptSet(
        name="Food",
        avoid=(
            "plastic textures",
            "unrealistic colors",
            "greasy overshine",
            "artificial food styling",
        ),
    ),
}


INDUSTRY_DOMAIN: dict[Industry, str] = {
    Industry.TECHNOLOGY: "technology",
    Industry.BUSINESS: "business",
    Industry.FINANCE: "business",
    Industry.MARKETING: "business",
    Industry.MEDICAL: "medical",
    Industry.HEALTHCARE: "healthcare",
    Industry.FOOD: "food",
}


def get_objects_to_avoid(
    industry: Industry,
    extra: list[str] | None = None,
) -> list[str]:
    """Merge universal, domain, and caller-provided avoid lists."""
    domain_key = INDUSTRY_DOMAIN.get(industry, "technology")
    domain = DOMAIN_NEGATIVES.get(domain_key)
    items: list[str] = list(UNIVERSAL_AVOID)
    if domain:
        items.extend(domain.avoid)
    # Technology + business are common together for SaaS content
    if industry in (Industry.TECHNOLOGY, Industry.GENERAL):
        items.extend(DOMAIN_NEGATIVES["business"].avoid)
    if extra:
        items.extend(extra)
    # Preserve order, drop duplicates
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def build_negative_prompt(
    industry: Industry,
    extra: list[str] | None = None,
) -> str:
    """Compose a natural-language negative prompt clause."""
    objects = get_objects_to_avoid(industry, extra)
    joined = ", ".join(objects)
    return f"Do not include any {joined}."
