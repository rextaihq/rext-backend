"""Industry-aware materials & texture library.

GPT Image responds strongly to concrete material cues (brushed metal,
frosted glass, matte ceramic) for photorealistic/3D renders — this was
entirely absent from the pipeline before.
"""

from __future__ import annotations

import random

from src.flow.image_generation.models import Industry

MATERIAL_PROFILES: dict[Industry, tuple[str, ...]] = {
    Industry.TECHNOLOGY: (
        "brushed aluminum surfaces",
        "frosted glass panels",
        "matte ceramic accents",
        "soft-touch polymer edges",
    ),
    Industry.BUSINESS: (
        "polished walnut and brushed steel",
        "tempered glass and matte stone",
        "woven upholstery textures",
    ),
    Industry.FINANCE: (
        "polished marble and brushed brass",
        "tempered glass and matte steel",
    ),
    Industry.MARKETING: (
        "matte painted surfaces with soft paper textures",
        "brushed metal with vibrant accent lacquer",
    ),
    Industry.MEDICAL: (
        "sterile matte white surfaces",
        "brushed medical-grade steel",
    ),
    Industry.HEALTHCARE: (
        "soft matte surfaces with warm fabric accents",
        "brushed steel and frosted glass",
    ),
    Industry.EDUCATION: (
        "matte wood and chalk-textured surfaces",
        "soft paper and canvas textures",
    ),
    Industry.FOOD: (
        "natural wood grain and woven linen",
        "matte ceramic and stoneware textures",
    ),
    Industry.GENERAL: ("matte painted surfaces and brushed metal accents",),
}


def resolve_materials(industry: Industry, seed: str = "") -> str:
    """Pick a short, natural materials clause for the given industry.

    `seed` (e.g. article title/keyword) keeps the choice stable for a given
    article while varying it across different articles/industries.
    """
    options = MATERIAL_PROFILES.get(industry, MATERIAL_PROFILES[Industry.GENERAL])
    if len(options) == 1:
        return options[0]
    rng = random.Random(seed or industry.value)
    return rng.choice(options)
