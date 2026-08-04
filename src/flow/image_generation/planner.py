"""Stage 1 — Image Planner.

Analyzes article metadata and produces an ImagePlanningContext.
"""

from __future__ import annotations

import re
from typing import Optional, Protocol

from src.flow.image_generation.color_library import detect_industry, resolve_color_palette
from src.flow.image_generation.content_type_mapper import (
    INTENT_GOAL_OVERRIDES,
    get_content_type_design,
    normalize_content_type,
)
from src.flow.image_generation.environment_library import resolve_environment
from src.flow.image_generation.models import (
    ArticleImageInput,
    ContentType,
    ImageGoal,
    ImagePlanningContext,
    ProductInfo,
    SearchIntent,
)
from src.flow.image_generation.negative_prompt_library import (
    build_negative_prompt,
    get_objects_to_avoid,
)
from src.flow.image_generation.style_library import get_style_profile, resolve_brand_style


class ContentTypeMapperProtocol(Protocol):
    def __call__(self, content_type: ContentType | str):
        ...


# Concrete visual metaphors for common B2B / tech topics. Matched on word
# boundaries (not raw substrings) so e.g. "blockchain" never false-matches
# the "ai" entry via the "chai" in "blockchain".
VISUAL_METAPHORS: dict[str, str] = {
    "saas": "a luminous cloud platform representing SaaS",
    "cloud": "a luminous multi-layer cloud infrastructure",
    "cloud computing": "a luminous multi-layer cloud infrastructure",
    "artificial intelligence": "a refined AI neural core with subtle data streams",
    "agentic ai": "a self-directing AI agent core with branching task pathways",
    "ai": "a refined AI neural core with subtle data streams",
    "machine learning": "a layered neural network sculpture of glowing nodes",
    "deep learning": "a layered neural network sculpture of glowing nodes",
    "generative ai": "a luminous generative core producing branching visual outputs",
    "large language model": "a luminous language core radiating structured text threads",
    "llm": "a luminous language core radiating structured text threads",
    "api": "an elegant API gateway connecting modular services",
    "microservices": "modular service blocks connected by clean data pathways",
    "kubernetes": "an orchestrated grid of connected containerized modules",
    "devops": "a streamlined CI/CD pipeline visualized as connected stages",
    "ci/cd": "a streamlined CI/CD pipeline visualized as connected stages",
    "automation": "a precise mechanical sequence of self-triggering process stages",
    "workflow automation": "a precise mechanical sequence of self-triggering process stages",
    "cybersecurity": "a protective security lattice around digital assets",
    "data security": "a protective security lattice around digital assets",
    "encryption": "a locked data vault wrapped in a protective geometric shell",
    "fintech": "a precise financial network flowing through secure nodes",
    "blockchain": "an interlocking chain of luminous verified data blocks",
    "cryptocurrency": "a suspended coin-like token orbited by verified transaction nodes",
    "marketing": "a focused brand signal radiating through connected channels",
    "content marketing": "a focused editorial signal radiating through connected channels",
    "seo": "a rising search-visibility beacon anchored in a content landscape",
    "analytics": "a layered dashboard of glowing data trend lines",
    "data analytics": "a layered dashboard of glowing data trend lines",
    "big data": "a dense luminous field of structured data particles",
    "collaboration": "connection nodes linking distributed team workstations",
    "remote work": "a distributed workspace connected by soft light pathways",
    "productivity": "a streamlined focused workspace with a single glowing task anchor",
    "e-commerce": "a floating storefront shelf with connected transaction pathways",
    "supply chain": "a connected sequence of logistics nodes across a transparent map",
    "customer experience": "a warm guided pathway leading toward a satisfied focal point",
    "onboarding": "a guided doorway pathway leading into a welcoming digital space",
    "no-code": "modular drag-and-drop building blocks assembling into a structure",
    "low-code": "modular drag-and-drop building blocks assembling into a structure",
    "open source": "interlocking collaborative code fragments forming a shared structure",
    "digital transformation": "an evolving structure shifting from analog to luminous digital form",
    "sustainability": "a balanced organic form intertwined with clean structured elements",
}


def _lookup_visual_metaphor(keyword_lower: str) -> str | None:
    """Return a concrete visual metaphor for a keyword, or None if unmapped.

    Longer/more specific keys are checked first so e.g. "agentic ai" wins
    over the plainer "ai" entry when both would match.
    """
    for key in sorted(VISUAL_METAPHORS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", keyword_lower):
            return VISUAL_METAPHORS[key]
    return None


class ImagePlanner:
    """Derive image requirements from article metadata.

    Single responsibility: turn ArticleImageInput into ImagePlanningContext.
    Does not compose final prompts or call image models.
    """

    def __init__(
        self,
        content_type_resolver: Optional[ContentTypeMapperProtocol] = None,
    ) -> None:
        self._get_design = content_type_resolver or get_content_type_design

    def plan(self, article: ArticleImageInput) -> ImagePlanningContext:
        """Build a strongly typed planning context from article input."""
        content_type = normalize_content_type(article.content_type)
        design = self._get_design(content_type)
        industry = detect_industry(
            title=article.title,
            summary=article.summary,
            primary_keyword=article.primary_keyword,
            secondary_keywords=article.secondary_keywords,
            industry_hint=article.industry_hint,
        )
        brand_style = resolve_brand_style(
            brand_voice=article.brand_voice,
            writing_style=article.writing_style,
            audience=article.audience,
            content_type=content_type.value,
            title=article.title,
            summary=article.summary,
        )
        style = get_style_profile(brand_style)
        palette = resolve_color_palette(industry, brand_style)

        topic = article.primary_keyword or article.title
        audience_label = self._audience_label(article.audience)
        primary_subject = self._derive_primary_subject(article, topic)
        supporting = self._derive_supporting_subjects(article, primary_subject)
        visual_story = design.story_template.format(
            topic=topic,
            audience=audience_label,
            subject=primary_subject,
        )

        image_goal = design.image_goal
        if article.search_intent in INTENT_GOAL_OVERRIDES:
            # Prefer intent-driven goals for commercial/transactional content
            if content_type not in (
                ContentType.TUTORIAL,
                ContentType.CHECKLIST,
                ContentType.HOW_TO_GUIDE,
                ContentType.DOCUMENTATION,
            ):
                image_goal = INTENT_GOAL_OVERRIDES[article.search_intent]

        communication_goal = self._communication_goal(
            image_goal=image_goal,
            topic=topic,
            audience_label=audience_label,
            search_intent=article.search_intent,
        )

        objects_to_avoid = get_objects_to_avoid(industry)
        negative_prompt = build_negative_prompt(industry)

        return ImagePlanningContext(
            image_goal=image_goal,
            communication_goal=communication_goal,
            image_intent=design.image_intent,
            image_type=design.image_type,
            audience=list(article.audience),
            visual_story=visual_story,
            primary_subject=primary_subject,
            supporting_subjects=supporting,
            environment=resolve_environment(design.environment_hint, industry),
            composition=f"{design.label}; {design.camera.value.replace('_', ' ')} framing",
            visual_hierarchy=(
                f"{primary_subject} as dominant focal point; "
                "supporting elements remain secondary and unobtrusive"
            ),
            focal_point=primary_subject,
            camera_angle=design.camera,
            depth="layered depth with soft background falloff",
            negative_space="approximately 35-40 percent open for title overlay",
            lighting=design.lighting,
            color_palette=palette,
            rendering_style=design.rendering_style,
            design_language=list(style.design_language),
            mood=list(style.mood),
            branding_style=brand_style,
            aspect_ratio=design.aspect_ratio,
            image_orientation=design.orientation,
            objects_to_avoid=objects_to_avoid,
            negative_prompt=negative_prompt,
            accessibility_considerations=[
                "sufficient subject-to-background contrast",
                "avoid relying on color alone to convey meaning",
                "keep focal subject large enough to read at thumbnail size",
                "leave clear negative space for overlaid titles",
            ],
            content_type=content_type,
            search_intent=article.search_intent,
            primary_keyword=article.primary_keyword,
            secondary_keywords=list(article.secondary_keywords),
            title=article.title,
            summary=article.summary,
            brand_voice=article.brand_voice,
            writing_style=article.writing_style,
            industry=industry,
            product=article.product,
        )

    @staticmethod
    def _audience_label(audience: list[str]) -> str:
        if not audience:
            return "professional readers"
        if len(audience) == 1:
            return audience[0]
        return f"{audience[0]} and related professionals"

    @staticmethod
    def _derive_primary_subject(article: ArticleImageInput, topic: str) -> str:
        product: ProductInfo | None = article.product
        if product and product.name:
            cues = ", ".join(product.visual_cues[:2]) if product.visual_cues else ""
            if cues:
                return f"{product.name} ({cues})"
            return product.name

        keyword = (article.primary_keyword or topic).strip()
        if not keyword:
            return "the central concept of the article"

        metaphor = _lookup_visual_metaphor(keyword.lower())
        if metaphor:
            return metaphor

        return f"a concrete visual centerpiece embodying {keyword}"

    @staticmethod
    def _derive_supporting_subjects(
        article: ArticleImageInput, primary_subject: str = ""
    ) -> list[str]:
        subjects: list[str] = []
        if article.audience:
            subjects.append(
                f"a small team of professionals representing {article.audience[0]}"
            )

        primary_tokens = set((article.primary_keyword or "").lower().split())
        for keyword in article.secondary_keywords:
            if len(subjects) >= 3:
                break
            keyword_lower = (keyword or "").lower().strip()
            keyword_tokens = set(keyword_lower.split())
            if not keyword_tokens:
                continue
            # Skip SEO variants that just elaborate on the primary keyword
            # (e.g. "agentic ai examples" when primary is "agentic ai") —
            # not a distinct visual concept, just search-phrase noise.
            if primary_tokens and primary_tokens.issubset(keyword_tokens):
                continue
            metaphor = _lookup_visual_metaphor(keyword_lower)
            if not metaphor or metaphor == primary_subject:
                # No concrete visual translation available — drop it rather
                # than emit the raw (non-visual) SEO keyword phrase.
                continue
            subjects.append(f"a quiet secondary presence of {metaphor}")

        if article.product and article.product.key_features:
            for feature in article.product.key_features[:2]:
                subjects.append(f"a quiet visual hint of {feature}")

        return subjects[:3]

    @staticmethod
    def _communication_goal(
        image_goal: ImageGoal,
        topic: str,
        audience_label: str,
        search_intent: SearchIntent,
    ) -> str:
        mapping = {
            ImageGoal.ATTRACT_ATTENTION: (
                f"Stop the scroll and establish credibility around {topic} for {audience_label}"
            ),
            ImageGoal.EXPLAIN_CONCEPT: (
                f"Make {topic} immediately understandable for {audience_label}"
            ),
            ImageGoal.BUILD_TRUST: (
                f"Communicate trust and real-world credibility around {topic}"
            ),
            ImageGoal.SHOWCASE_PRODUCT: (
                f"Present the product value of {topic} with clarity and desire"
            ),
            ImageGoal.GUIDE_PROCESS: (
                f"Visually guide {audience_label} through the process of {topic}"
            ),
            ImageGoal.SUPPORT_NARRATIVE: (
                f"Support the article narrative on {topic} with a refined visual thesis"
            ),
            ImageGoal.DRIVE_CONVERSION: (
                f"Create desire and conversion momentum around {topic} "
                f"({search_intent.value} intent)"
            ),
        }
        return mapping.get(
            image_goal,
            f"Communicate the essence of {topic} to {audience_label}",
        )
