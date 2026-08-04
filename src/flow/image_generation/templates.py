"""Reusable prompt templates for the Image Prompt Composer.

Templates are kept outside business logic so composers and future
model adapters can swap formatting without changing planning stages.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    """Named format-string template."""

    name: str
    body: str


# Artist-instruction style template (default for OpenAI / GPT Image)
ARTIST_INSTRUCTION_TEMPLATE = PromptTemplate(
    name="artist_instruction",
    body=(
        "Create a {style_adjectives} {design_label} for a {content_type_label}. "
        "Depict {visual_story} within {environment}. "
        "Use a {composition_framing} with {typography_space}. "
        "Render the scene as a sophisticated {rendering_style_label} using "
        "{lighting_label}, a {background_color} background, "
        "{primary_color} and {secondary_color} primary colors"
        "{accent_clause}. "
        "Materials and surfaces: {materials}. "
        "Keep {focal_point} as the primary focal point while supporting "
        "elements remain subtle{supporting_clause}. "
        "Camera: {camera_label}. Perspective: {perspective}. "
        "Depth: {depth}. "
        "The mood should communicate {mood}. "
        "{accessibility_clause}"
        "{negative_clause}"
    ),
)


# Midjourney-oriented condensed template (future adapter)
MIDJOURNEY_TEMPLATE = PromptTemplate(
    name="midjourney",
    body=(
        "{visual_story}, {primary_subject}, {environment}, "
        "{rendering_style_label}, {lighting_label}, {camera_label}, "
        "{primary_color} {secondary_color} palette, {mood}, "
        "{composition_framing}, --no {negative_short}"
    ),
)


# Flux / Ideogram short natural prompt
FLUX_TEMPLATE = PromptTemplate(
    name="flux",
    body=(
        "{style_adjectives} {design_label}: {visual_story}. "
        "Primary subject: {primary_subject}. Environment: {environment}. "
        "Style: {rendering_style_label}, {lighting_label}, {camera_label}. "
        "Materials: {materials}. "
        "Colors: {primary_color}, {secondary_color}, {background_color}. "
        "Composition: {composition_framing}; focal point: {focal_point}. "
        "Mood: {mood}. Avoid: {negative_short}."
    ),
)


TEMPLATES: dict[str, PromptTemplate] = {
    ARTIST_INSTRUCTION_TEMPLATE.name: ARTIST_INSTRUCTION_TEMPLATE,
    MIDJOURNEY_TEMPLATE.name: MIDJOURNEY_TEMPLATE,
    FLUX_TEMPLATE.name: FLUX_TEMPLATE,
}


RENDERING_STYLE_LABELS: dict[str, str] = {
    "photorealistic": "photorealistic image",
    "3d_render": "3D editorial illustration",
    "editorial_illustration": "editorial illustration",
    "vector_illustration": "vector illustration",
    "watercolor": "watercolor illustration",
    "minimal": "minimal illustration",
    "abstract": "abstract visual",
    "flat_illustration": "flat illustration",
    "isometric": "isometric illustration",
    "blueprint": "technical blueprint illustration",
    "product_showcase": "product showcase render",
    "cinematic": "cinematic still",
}


LIGHTING_LABELS: dict[str, str] = {
    "studio": "clean studio lighting",
    "natural": "natural daylight",
    "volumetric": "soft volumetric lighting",
    "hdr": "HDR lighting",
    "cyber": "cyber lighting",
    "neon": "restrained neon accents",
    "ambient": "soft ambient lighting",
    "dramatic": "dramatic directional lighting",
    "soft": "soft diffused lighting",
}


CAMERA_LABELS: dict[str, str] = {
    "eye_level": "eye-level view",
    "wide": "wide cinematic view",
    "top_down": "top-down view",
    "isometric": "isometric camera",
    "drone": "elevated drone perspective",
    "close_up": "close-up framing",
    "macro": "macro detail framing",
    "architectural": "architectural perspective",
}


CONTENT_TYPE_LABELS: dict[str, str] = {
    "blog": "technology blog",
    "tutorial": "tutorial article",
    "how_to_guide": "how-to guide",
    "checklist": "checklist article",
    "case_study": "case study",
    "whitepaper": "whitepaper",
    "explainer": "explainer article",
    "pillar_content": "pillar content page",
    "faq": "FAQ page",
    "glossary": "glossary entry",
    "resource_list": "resource list page",
    "news": "news article",
    "comparison": "comparison article",
    "best_tools": "best tools roundup",
    "alternatives": "alternatives guide",
    "product_review": "product review",
    "pros_cons": "pros and cons article",
    "product_roundup": "product roundup",
    "buying_guide": "buying guide",
    "brand_page": "brand page",
    "product_homepage": "product homepage",
    "feature_overview": "feature overview page",
    "documentation": "documentation page",
    "login_guide": "login guide",
    "contact_us": "contact us page",
    "about_us": "about us page",
    "help_center": "help center page",
    "landing_page": "landing page",
    "sales_page": "sales page",
    "pricing_page": "pricing page",
    "signup_page": "signup page",
    "demo_page": "demo page",
    "coupon_page": "coupon page",
    "checkout_page": "checkout page",
    "service_page": "service page",
}


ASPECT_RATIO_TO_SIZE: dict[str, str] = {
    "1:1": "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "3:2": "1792x1024",
    "4:3": "1792x1024",
}
