"""Stage 2 — Art Director.

Enriches ImagePlanningContext with professional design decisions.
"""

from __future__ import annotations

from typing import Optional, Protocol

from src.flow.image_generation.color_library import resolve_color_palette
from src.flow.image_generation.composition_library import (
    build_composition_direction,
    get_composition_preset,
    resolve_composition_style,
)
from src.flow.image_generation.models import (
    ArtDirection,
    BrandStyle,
    CameraAngle,
    FocusLayers,
    ImagePlanningContext,
    LightingStyle,
    RenderingStyle,
)
from src.flow.image_generation.style_library import get_style_profile


class StyleResolverProtocol(Protocol):
    def __call__(self, style: BrandStyle): ...


# Content / brand driven rendering overrides
BRAND_RENDERING: dict[BrandStyle, RenderingStyle] = {
    BrandStyle.PREMIUM_SAAS: RenderingStyle.THREE_D_RENDER,
    BrandStyle.STARTUP: RenderingStyle.FLAT_ILLUSTRATION,
    BrandStyle.LUXURY: RenderingStyle.CINEMATIC,
    BrandStyle.DEVELOPER: RenderingStyle.EDITORIAL_ILLUSTRATION,
    BrandStyle.CORPORATE: RenderingStyle.PHOTOREALISTIC,
    BrandStyle.FRIENDLY: RenderingStyle.FLAT_ILLUSTRATION,
    BrandStyle.EDITORIAL: RenderingStyle.PHOTOREALISTIC,
}

BRAND_LIGHTING: dict[BrandStyle, LightingStyle] = {
    BrandStyle.PREMIUM_SAAS: LightingStyle.VOLUMETRIC,
    BrandStyle.STARTUP: LightingStyle.SOFT,
    BrandStyle.LUXURY: LightingStyle.DRAMATIC,
    BrandStyle.DEVELOPER: LightingStyle.CYBER,
    BrandStyle.CORPORATE: LightingStyle.NATURAL,
    BrandStyle.FRIENDLY: LightingStyle.SOFT,
    BrandStyle.EDITORIAL: LightingStyle.NATURAL,
}

BRAND_CAMERA: dict[BrandStyle, CameraAngle] = {
    BrandStyle.PREMIUM_SAAS: CameraAngle.WIDE,
    BrandStyle.STARTUP: CameraAngle.EYE_LEVEL,
    BrandStyle.LUXURY: CameraAngle.WIDE,
    BrandStyle.DEVELOPER: CameraAngle.CLOSE_UP,
    BrandStyle.CORPORATE: CameraAngle.EYE_LEVEL,
    BrandStyle.FRIENDLY: CameraAngle.EYE_LEVEL,
    BrandStyle.EDITORIAL: CameraAngle.EYE_LEVEL,
}


class ArtDirector:
    """Enrich planning context like an experienced creative director.

    Single responsibility: composition, focus layers, rendering, lighting,
    camera, palette, and brand language. Does not write the final prompt.
    """

    def __init__(
        self,
        style_resolver: Optional[StyleResolverProtocol] = None,
    ) -> None:
        self._get_style = style_resolver or get_style_profile

    def direct(self, context: ImagePlanningContext) -> ImagePlanningContext:
        """Return a copy of context enriched with ArtDirection."""
        brand_style = context.branding_style
        style = self._get_style(brand_style)

        composition_style = resolve_composition_style(
            image_type=context.image_type,
            content_type=context.content_type,
        )
        composition = build_composition_direction(composition_style)
        preset = get_composition_preset(composition_style)

        rendering = self._choose_rendering(context, brand_style)
        lighting = self._choose_lighting(context, brand_style)
        camera = self._choose_camera(context, brand_style)
        palette = resolve_color_palette(context.industry, brand_style)

        focus = FocusLayers(
            primary_focus=context.focal_point or context.primary_subject,
            secondary_focus=(
                context.supporting_subjects[0]
                if context.supporting_subjects
                else "quiet environmental context"
            ),
            supporting_elements=list(context.supporting_subjects),
            background=context.environment or "soft unobtrusive environment",
            foreground="minimal foreground detail that deepens space without clutter",
            negative_space=preset.negative_space,
        )

        mood = list(dict.fromkeys([*context.mood, *style.mood]))
        design_language = list(
            dict.fromkeys([*context.design_language, *style.design_language, *style.adjectives[:5]])
        )

        art_direction = ArtDirection(
            composition=composition,
            focus=focus,
            rendering_style=rendering,
            lighting=lighting,
            camera=camera,
            color_palette=palette,
            brand_style=brand_style,
            design_language=design_language,
            mood=mood,
            industry=context.industry,
        )

        # Merge art direction decisions back onto the planning context
        return context.model_copy(
            update={
                "art_direction": art_direction,
                "composition": (
                    f"{composition.framing}; {composition.balance}; {composition.typography_space}"
                ),
                "visual_hierarchy": composition.visual_hierarchy,
                "focal_point": focus.primary_focus,
                "camera_angle": camera,
                "perspective": preset.perspective,
                "depth": composition.depth,
                "negative_space": focus.negative_space,
                "lighting": lighting,
                "color_palette": palette,
                "rendering_style": rendering,
                "design_language": design_language,
                "mood": mood,
                "branding_style": brand_style,
            }
        )

    @staticmethod
    def _choose_rendering(
        context: ImagePlanningContext,
        brand_style: BrandStyle,
    ) -> RenderingStyle:
        # Preserve content-type design-system rendering choices
        locked = {
            RenderingStyle.PHOTOREALISTIC,
            RenderingStyle.PRODUCT_SHOWCASE,
            RenderingStyle.BLUEPRINT,
            RenderingStyle.ISOMETRIC,
            RenderingStyle.FLAT_ILLUSTRATION,
            RenderingStyle.MINIMAL,
            RenderingStyle.ABSTRACT,
            RenderingStyle.WATERCOLOR,
            RenderingStyle.VECTOR_ILLUSTRATION,
        }
        if context.rendering_style in locked:
            return context.rendering_style
        return BRAND_RENDERING.get(brand_style, context.rendering_style)

    @staticmethod
    def _choose_lighting(
        context: ImagePlanningContext,
        brand_style: BrandStyle,
    ) -> LightingStyle:
        if context.rendering_style == RenderingStyle.PHOTOREALISTIC:
            return LightingStyle.NATURAL
        return BRAND_LIGHTING.get(brand_style, context.lighting)

    @staticmethod
    def _choose_camera(
        context: ImagePlanningContext,
        brand_style: BrandStyle,
    ) -> CameraAngle:
        locked = {
            CameraAngle.ISOMETRIC,
            CameraAngle.TOP_DOWN,
            CameraAngle.MACRO,
        }
        if context.camera_angle in locked:
            return context.camera_angle
        return BRAND_CAMERA.get(brand_style, context.camera_angle)
