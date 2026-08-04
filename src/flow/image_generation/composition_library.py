"""Composition presets for editorial image direction."""

from __future__ import annotations

from dataclasses import dataclass

from src.flow.image_generation.models import (
    CompositionDirection,
    CompositionStyle,
    ContentType,
    ImageType,
)


@dataclass(frozen=True)
class CompositionPreset:
    """Reusable composition recipe."""

    style: CompositionStyle
    framing: str
    balance: str
    symmetry: str
    rule_of_thirds: bool
    leading_lines: str
    spacing: str
    depth: str
    contrast: str
    color_harmony: str
    typography_space: str
    visual_hierarchy: str
    negative_space: str
    perspective: str


COMPOSITION_PRESETS: dict[CompositionStyle, CompositionPreset] = {
    CompositionStyle.WIDE_CINEMATIC: CompositionPreset(
        style=CompositionStyle.WIDE_CINEMATIC,
        framing="wide cinematic establishing frame",
        balance="asymmetrical with left-weighted subject mass",
        symmetry="intentional asymmetry",
        rule_of_thirds=True,
        leading_lines="subtle converging lines toward the primary subject",
        spacing="generous breathing room around the focal subject",
        depth="clear foreground, midground, and soft background layers",
        contrast="high subject-to-background contrast",
        color_harmony="restrained complementary accents",
        typography_space="approximately 40 percent negative space in the upper-left for title overlay",
        visual_hierarchy="primary subject dominates; supporting elements remain quiet",
        negative_space="approximately 40 percent reserved in the upper-left",
        perspective="slightly elevated wide perspective",
    ),
    CompositionStyle.RULE_OF_THIRDS: CompositionPreset(
        style=CompositionStyle.RULE_OF_THIRDS,
        framing="subject anchored on a rule-of-thirds intersection",
        balance="classic thirds balance",
        symmetry="asymmetric balance",
        rule_of_thirds=True,
        leading_lines="soft environmental lines guiding the eye to the subject",
        spacing="open margins on the opposite third",
        depth="moderate depth with soft background separation",
        contrast="clear subject separation",
        color_harmony="harmonized neutrals with one accent",
        typography_space="open third reserved for overlay text",
        visual_hierarchy="single dominant subject with quiet supports",
        negative_space="one open third reserved for typography",
        perspective="eye-level observational perspective",
    ),
    CompositionStyle.SPLIT: CompositionPreset(
        style=CompositionStyle.SPLIT,
        framing="balanced split-frame composition",
        balance="equal visual weight across two panels",
        symmetry="mirrored structural balance",
        rule_of_thirds=False,
        leading_lines="central divider guiding comparison reading",
        spacing="clear gutter between compared subjects",
        depth="shallow depth to keep both sides equally readable",
        contrast="side-to-side contrast for comparison clarity",
        color_harmony="paired palettes with shared neutrals",
        typography_space="top band reserved for labels if needed",
        visual_hierarchy="two equal primary subjects",
        negative_space="central gutter and top margin kept clear",
        perspective="front-facing comparative perspective",
    ),
    CompositionStyle.LAYERED_DEPTH: CompositionPreset(
        style=CompositionStyle.LAYERED_DEPTH,
        framing="layered process scene with progressive depth",
        balance="left-to-right visual flow",
        symmetry="rhythmic asymmetry",
        rule_of_thirds=True,
        leading_lines="process pathway leading through stages",
        spacing="even stage spacing with breathing room",
        depth="strong layered depth across workflow stages",
        contrast="progressive emphasis on the active stage",
        color_harmony="sequential accent progression",
        typography_space="upper margin kept light for captions",
        visual_hierarchy="active stage first, prior stages quieter",
        negative_space="margins kept open to avoid clutter",
        perspective="slight isometric or elevated process view",
    ),
    CompositionStyle.NEGATIVE_SPACE_HEAVY: CompositionPreset(
        style=CompositionStyle.NEGATIVE_SPACE_HEAVY,
        framing="minimal subject with expansive open field",
        balance="sparse asymmetrical balance",
        symmetry="open asymmetry",
        rule_of_thirds=True,
        leading_lines="almost none; quiet geometry only",
        spacing="maximum breathing room",
        depth="shallow elegant depth",
        contrast="soft subject against calm field",
        color_harmony="monochrome field with one accent",
        typography_space="large open region for executive typography",
        visual_hierarchy="one concise subject only",
        negative_space="approximately 50 percent open field",
        perspective="clean frontal or soft elevated view",
    ),
    CompositionStyle.CENTERED: CompositionPreset(
        style=CompositionStyle.CENTERED,
        framing="centered hero subject",
        balance="centered formal balance",
        symmetry="radial or bilateral symmetry",
        rule_of_thirds=False,
        leading_lines="radial lines toward the center",
        spacing="equal surrounding margin",
        depth="subject pops from soft background blur",
        contrast="strong center emphasis",
        color_harmony="center accent against muted surround",
        typography_space="outer margins reserved for overlay",
        visual_hierarchy="single centered hero",
        negative_space="surrounding margins kept clean",
        perspective="front-facing hero perspective",
    ),
    CompositionStyle.LEADING_LINES: CompositionPreset(
        style=CompositionStyle.LEADING_LINES,
        framing="architectural or environmental corridor frame",
        balance="directional balance toward the subject",
        symmetry="guided asymmetry",
        rule_of_thirds=True,
        leading_lines="strong environmental lines pulling toward the focal point",
        spacing="open path around the subject",
        depth="deep vanishing-point depth",
        contrast="bright subject against darker pathway",
        color_harmony="cool pathway with warm subject accent",
        typography_space="upper sky or open wall kept clear",
        visual_hierarchy="destination subject first",
        negative_space="open upper plane for title overlay",
        perspective="architectural vanishing-point perspective",
    ),
    CompositionStyle.ASYMMETRICAL: CompositionPreset(
        style=CompositionStyle.ASYMMETRICAL,
        framing="dynamic off-center editorial frame",
        balance="weighted asymmetry",
        symmetry="deliberate imbalance",
        rule_of_thirds=True,
        leading_lines="diagonal energy toward the subject",
        spacing="uneven but intentional margins",
        depth="active layered depth",
        contrast="bold subject isolation",
        color_harmony="accent-forward editorial harmony",
        typography_space="lighter side reserved for overlay",
        visual_hierarchy="bold primary with light secondary support",
        negative_space="open lighter side for text",
        perspective="dynamic wide editorial angle",
    ),
    CompositionStyle.SYMMETRICAL: CompositionPreset(
        style=CompositionStyle.SYMMETRICAL,
        framing="formal symmetrical presentation",
        balance="perfect bilateral balance",
        symmetry="mirror symmetry",
        rule_of_thirds=False,
        leading_lines="central axis alignment",
        spacing="equal left-right margins",
        depth="controlled formal depth",
        contrast="balanced tonal contrast",
        color_harmony="mirrored color weights",
        typography_space="top or bottom centered band",
        visual_hierarchy="central subject with mirrored supports",
        negative_space="equal open margins",
        perspective="formal frontal perspective",
    ),
}


IMAGE_TYPE_COMPOSITION: dict[ImageType, CompositionStyle] = {
    ImageType.EDITORIAL_HERO: CompositionStyle.WIDE_CINEMATIC,
    ImageType.WORKFLOW: CompositionStyle.LAYERED_DEPTH,
    ImageType.PROCESS: CompositionStyle.LAYERED_DEPTH,
    ImageType.BUSINESS_PHOTO: CompositionStyle.RULE_OF_THIRDS,
    ImageType.EXECUTIVE_MINIMAL: CompositionStyle.NEGATIVE_SPACE_HEAVY,
    ImageType.SPLIT_LAYOUT: CompositionStyle.SPLIT,
    ImageType.HERO_MARKETING: CompositionStyle.WIDE_CINEMATIC,
    ImageType.TECHNICAL: CompositionStyle.CENTERED,
    ImageType.CONCEPT: CompositionStyle.NEGATIVE_SPACE_HEAVY,
    ImageType.EDITORIAL_PHOTO: CompositionStyle.RULE_OF_THIRDS,
    ImageType.FRIENDLY_MINIMAL: CompositionStyle.NEGATIVE_SPACE_HEAVY,
    ImageType.HUMAN_CENTRIC: CompositionStyle.RULE_OF_THIRDS,
    ImageType.PRODUCT_SHOWCASE: CompositionStyle.CENTERED,
    ImageType.PRODUCT_GRID: CompositionStyle.LAYERED_DEPTH,
    ImageType.COMPARISON_ROUNDUP: CompositionStyle.ASYMMETRICAL,
    ImageType.BRAND_IDENTITY: CompositionStyle.CENTERED,
    ImageType.FEATURE_HIGHLIGHT: CompositionStyle.RULE_OF_THIRDS,
    ImageType.CONVERSION_HERO: CompositionStyle.WIDE_CINEMATIC,
    ImageType.PRICING_VISUAL: CompositionStyle.SYMMETRICAL,
    ImageType.RESOURCE_COLLECTION: CompositionStyle.LAYERED_DEPTH,
}


CONTENT_TYPE_COMPOSITION: dict[ContentType, CompositionStyle] = {
    ContentType.COMPARISON: CompositionStyle.SPLIT,
    ContentType.PROS_CONS: CompositionStyle.SPLIT,
    ContentType.WHITEPAPER: CompositionStyle.NEGATIVE_SPACE_HEAVY,
    ContentType.TUTORIAL: CompositionStyle.LAYERED_DEPTH,
    ContentType.CHECKLIST: CompositionStyle.LAYERED_DEPTH,
    ContentType.LANDING_PAGE: CompositionStyle.WIDE_CINEMATIC,
    ContentType.SALES_PAGE: CompositionStyle.WIDE_CINEMATIC,
    ContentType.DOCUMENTATION: CompositionStyle.CENTERED,
    ContentType.PRICING_PAGE: CompositionStyle.SYMMETRICAL,
    ContentType.BEST_TOOLS: CompositionStyle.LAYERED_DEPTH,
    ContentType.PRODUCT_ROUNDUP: CompositionStyle.LAYERED_DEPTH,
}


def get_composition_preset(style: CompositionStyle) -> CompositionPreset:
    """Return a composition preset."""
    return COMPOSITION_PRESETS.get(style, COMPOSITION_PRESETS[CompositionStyle.WIDE_CINEMATIC])


def resolve_composition_style(
    image_type: ImageType,
    content_type: ContentType | None = None,
) -> CompositionStyle:
    """Choose composition style from image and content type."""
    if content_type and content_type in CONTENT_TYPE_COMPOSITION:
        return CONTENT_TYPE_COMPOSITION[content_type]
    return IMAGE_TYPE_COMPOSITION.get(image_type, CompositionStyle.WIDE_CINEMATIC)


def build_composition_direction(style: CompositionStyle) -> CompositionDirection:
    """Convert a preset into a CompositionDirection model."""
    preset = get_composition_preset(style)
    return CompositionDirection(
        style=preset.style,
        framing=preset.framing,
        balance=preset.balance,
        symmetry=preset.symmetry,
        rule_of_thirds=preset.rule_of_thirds,
        leading_lines=preset.leading_lines,
        spacing=preset.spacing,
        depth=preset.depth,
        contrast=preset.contrast,
        color_harmony=preset.color_harmony,
        typography_space=preset.typography_space,
        visual_hierarchy=preset.visual_hierarchy,
    )
