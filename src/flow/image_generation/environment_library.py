"""Industry-aware environment texture library.

Blends the content type's environment archetype (from content_type_mapper)
with an industry-specific texture clause so the same content type doesn't
render an identical environment sentence for every industry.
"""

from __future__ import annotations

from src.flow.image_generation.models import Industry


INDUSTRY_ENVIRONMENT_TEXTURE: dict[Industry, str] = {
    Industry.TECHNOLOGY: "clean monitors, soft device glow, and minimal cable-free surfaces",
    Industry.BUSINESS: "glass partitions and understated corporate furnishings",
    Industry.FINANCE: "precise, muted surfaces and quiet institutional detail",
    Industry.MARKETING: "bright creative-studio textures and open work surfaces",
    Industry.MEDICAL: "calm clinical surfaces and soft, sterile light",
    Industry.HEALTHCARE: "warm clinical surfaces and reassuring soft light",
    Industry.EDUCATION: "bright, open learning-space textures",
    Industry.FOOD: "warm tactile culinary textures",
    Industry.GENERAL: "understated professional textures",
}


def resolve_environment(environment_hint: str, industry: Industry) -> str:
    """Blend a content-type environment archetype with industry texture."""
    texture = INDUSTRY_ENVIRONMENT_TEXTURE.get(
        industry, INDUSTRY_ENVIRONMENT_TEXTURE[Industry.GENERAL]
    )
    if not environment_hint:
        return texture
    return f"{environment_hint} featuring {texture}"
