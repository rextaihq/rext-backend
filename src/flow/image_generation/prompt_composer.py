"""Stage 3 — Image Prompt Composer.

Merges planning context, art direction, brand style, and negative prompts
into a natural artist-instruction prompt. Model-agnostic via templates.
"""

from __future__ import annotations

import random
from typing import Optional, Protocol

from src.flow.image_generation.content_type_mapper import get_content_type_design
from src.flow.image_generation.materials_library import resolve_materials
from src.flow.image_generation.models import ComposedImagePrompt, ImagePlanningContext
from src.flow.image_generation.style_library import get_style_profile
from src.flow.image_generation.templates import (
    ASPECT_RATIO_TO_SIZE,
    CAMERA_LABELS,
    CONTENT_TYPE_LABELS,
    LIGHTING_LABELS,
    RENDERING_STYLE_LABELS,
    TEMPLATES,
    PromptTemplate,
)


class TemplateProvider(Protocol):
    def get(self, name: str) -> PromptTemplate | None:
        ...


class ImagePromptComposer:
    """Compose a final image prompt from an enriched planning context.

    Swap templates / format hints to target OpenAI, Flux, Ideogram,
    or Midjourney-compatible formats without changing planner or art director.
    """

    def __init__(
        self,
        template_name: str = "artist_instruction",
        format_hint: str = "openai",
        templates: Optional[dict[str, PromptTemplate]] = None,
    ) -> None:
        self.template_name = template_name
        self.format_hint = format_hint
        self._templates = templates or TEMPLATES

    def compose(self, context: ImagePlanningContext) -> ComposedImagePrompt:
        """Merge planning + art direction + brand + negatives into one prompt."""
        template = self._templates.get(self.template_name) or self._templates["artist_instruction"]
        variables = self._build_variables(context)
        prompt = " ".join(template.body.format(**variables).split())
        negative = context.negative_prompt or variables["negative_clause"]

        style = get_style_profile(context.branding_style)
        aspect = context.aspect_ratio
        size = ASPECT_RATIO_TO_SIZE.get(aspect.value, "1792x1024")

        return ComposedImagePrompt(
            prompt=prompt,
            negative_prompt=negative,
            planning_context=context,
            aspect_ratio=aspect,
            recommended_size=size,
            style_tags=list(style.adjectives),
            format_hint=self.format_hint,
        )

    def _build_variables(self, context: ImagePlanningContext) -> dict[str, str]:
        art = context.art_direction
        style = get_style_profile(context.branding_style)
        design = get_content_type_design(context.content_type)
        palette = (art.color_palette if art else context.color_palette)
        composition = art.composition if art else None

        rendering_key = (
            art.rendering_style.value if art else context.rendering_style.value
        )
        lighting_key = art.lighting.value if art else context.lighting.value
        camera_key = art.camera.value if art else context.camera_angle.value

        supporting = context.supporting_subjects
        if supporting:
            supporting_clause = (
                ", with "
                + ", ".join(supporting[:3])
                + " kept understated in the periphery"
            )
        else:
            supporting_clause = ""

        accent = palette.accent or ""
        accent_clause = (
            f" with restrained {accent} accents" if accent else ""
        )

        mood_values = art.mood if art and art.mood else context.mood
        mood = ", ".join(mood_values) if mood_values else "clarity and professionalism"

        objects = context.objects_to_avoid
        if objects:
            # Prefer a readable subset in the main prompt; full list stays on context
            negative_short = ", ".join(objects[:14])
            negative_clause = (
                "Do not include any "
                + ", ".join(objects)
                + "."
            )
        else:
            negative_short = "text, logos, watermarks, clutter"
            negative_clause = context.negative_prompt or (
                "Do not include any readable text, logos, watermarks, or clutter."
            )

        content_label = CONTENT_TYPE_LABELS.get(
            context.content_type.value,
            context.content_type.value.replace("_", " "),
        )

        # Seed controlled variation from the article itself: same article
        # always composes the same prompt, but different articles vary
        # instead of always emitting the identical adjective ordering.
        seed = context.primary_keyword or context.title or context.visual_story
        rng = random.Random(seed)
        adjective_pool = [
            a for a in style.adjectives if a.lower() not in design.label.lower()
        ] or list(style.adjectives)
        sample_size = min(4, len(adjective_pool))
        style_adjectives = ", ".join(
            sorted(rng.sample(adjective_pool, sample_size), key=adjective_pool.index)
        )

        # Avoid restating the primary subject verbatim twice in one prompt —
        # the visual_story clause already names it in full.
        focal_point = context.focal_point or context.primary_subject
        focal_point_label = (
            "this same central subject"
            if focal_point and focal_point == context.primary_subject
            else focal_point
        )

        camera_label = CAMERA_LABELS.get(camera_key, camera_key.replace("_", " "))
        if rendering_key == "photorealistic":
            camera_label = f"{camera_label}, 35mm lens, shallow depth of field"

        base_depth = composition.depth if composition else context.depth
        anchor_subjects = [
            s for s in [context.primary_subject, *context.supporting_subjects[:1]] if s
        ]
        depth = (
            f"{base_depth}, with {' and '.join(anchor_subjects)} anchoring the near layers"
            if anchor_subjects
            else base_depth
        )

        accessibility = context.accessibility_considerations
        accessibility_clause = (
            f"Ensure {', '.join(accessibility[:2])}. " if accessibility else ""
        )

        materials = resolve_materials(context.industry, seed=seed)

        return {
            "style_adjectives": style_adjectives,
            "design_label": design.label.lower(),
            "content_type_label": content_label,
            "visual_story": context.visual_story.rstrip("."),
            "primary_subject": context.primary_subject,
            "supporting_clause": supporting_clause,
            "environment": context.environment,
            "composition_framing": (
                composition.framing if composition else context.composition
            ),
            "typography_space": (
                composition.typography_space
                if composition
                else context.negative_space
            ),
            "rendering_style_label": RENDERING_STYLE_LABELS.get(
                rendering_key, rendering_key.replace("_", " ")
            ),
            "lighting_label": LIGHTING_LABELS.get(
                lighting_key, lighting_key.replace("_", " ")
            ),
            "background_color": palette.background or "neutral dark field",
            "primary_color": palette.primary,
            "secondary_color": palette.secondary or palette.primary,
            "accent_clause": accent_clause,
            "materials": materials,
            "focal_point": focal_point_label,
            "camera_label": camera_label,
            "perspective": context.perspective,
            "depth": depth,
            "mood": mood,
            "accessibility_clause": accessibility_clause,
            "negative_clause": negative_clause,
            "negative_short": negative_short,
        }
