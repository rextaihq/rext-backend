"""Image Planning Pipeline orchestrator.

Article → Planner → Art Director → Prompt Composer → ComposedImagePrompt

Stages are injectable so tests and future model adapters can swap pieces.
"""

from __future__ import annotations

from typing import Optional

from src.flow.image_generation.art_director import ArtDirector
from src.flow.image_generation.content_type_mapper import normalize_content_type
from src.flow.image_generation.models import (
    ArticleImageInput,
    ComposedImagePrompt,
    ImagePlanningContext,
    ProductInfo,
    SearchIntent,
)
from src.flow.image_generation.planner import ImagePlanner
from src.flow.image_generation.prompt_composer import ImagePromptComposer


class ImagePlanningPipeline:
    """Orchestrates planner → art director → prompt composer.

    Model-agnostic: only the composer (and optional format_hint) need to
    change when targeting Flux, Ideogram, Midjourney, etc.
    """

    def __init__(
        self,
        planner: Optional[ImagePlanner] = None,
        art_director: Optional[ArtDirector] = None,
        composer: Optional[ImagePromptComposer] = None,
    ) -> None:
        self.planner = planner or ImagePlanner()
        self.art_director = art_director or ArtDirector()
        self.composer = composer or ImagePromptComposer()

    def run(self, article: ArticleImageInput) -> ComposedImagePrompt:
        """Execute the full planning pipeline."""
        brief = self.planner.plan(article)
        directed = self.art_director.direct(brief)
        return self.composer.compose(directed)

    def plan_only(self, article: ArticleImageInput) -> ImagePlanningContext:
        """Return planning context without composing a prompt."""
        return self.planner.plan(article)

    def direct_only(self, article: ArticleImageInput) -> ImagePlanningContext:
        """Return art-directed context without composing a prompt."""
        return self.art_director.direct(self.planner.plan(article))


def build_article_input(
    title: str,
    summary: str = "",
    content_type: str = "blog",
    search_intent: str = "informational",
    primary_keyword: str = "",
    secondary_keywords: list[str] | str | None = None,
    audience: list[str] | str | None = None,
    brand_voice: str = "",
    writing_style: str = "",
    product_name: str = "",
    product_description: str = "",
    industry_hint: str | None = None,
) -> ArticleImageInput:
    """Helper to build ArticleImageInput from loose tool / agent arguments."""

    def _as_list(value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [v.strip() for v in value if v and str(v).strip()]
        return [part.strip() for part in str(value).split(",") if part.strip()]

    try:
        intent = SearchIntent(search_intent.strip().lower())
    except ValueError:
        intent = SearchIntent.INFORMATIONAL

    product = None
    if product_name or product_description:
        product = ProductInfo(
            name=product_name or None,
            description=product_description or None,
        )

    return ArticleImageInput(
        title=title,
        summary=summary,
        content_type=normalize_content_type(content_type),
        search_intent=intent,
        primary_keyword=primary_keyword,
        secondary_keywords=_as_list(secondary_keywords),
        audience=_as_list(audience),
        brand_voice=brand_voice,
        writing_style=writing_style,
        product=product,
        industry_hint=industry_hint,
    )


def compose_image_prompt(
    title: str,
    summary: str = "",
    content_type: str = "blog",
    search_intent: str = "informational",
    primary_keyword: str = "",
    secondary_keywords: list[str] | str | None = None,
    audience: list[str] | str | None = None,
    brand_voice: str = "",
    writing_style: str = "",
    product_name: str = "",
    product_description: str = "",
    industry_hint: str | None = None,
    pipeline: Optional[ImagePlanningPipeline] = None,
) -> ComposedImagePrompt:
    """Convenience entry point used by agent tools and services."""
    article = build_article_input(
        title=title,
        summary=summary,
        content_type=content_type,
        search_intent=search_intent,
        primary_keyword=primary_keyword,
        secondary_keywords=secondary_keywords,
        audience=audience,
        brand_voice=brand_voice,
        writing_style=writing_style,
        product_name=product_name,
        product_description=product_description,
        industry_hint=industry_hint,
    )
    active = pipeline or ImagePlanningPipeline()
    return active.run(article)
