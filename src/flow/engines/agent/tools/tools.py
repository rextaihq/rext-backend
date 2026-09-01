import asyncio
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from dotenv import load_dotenv
from openai import AsyncOpenAI
import base64
import json
import os
import uuid

from src.flow.image_generation import compose_image_prompt
from src.api.config import settings

load_dotenv()

SEARCH_HARD_CAP = 6

DEFAULT_IMAGE_MODEL = "gpt-image-2-2026-04-21"

# Higher-stakes / conversion-facing hero imagery gets a higher quality tier;
# everything else stays on the cheaper default. Without this, every image
# (blog hero, landing page, marketing) was capped at the lowest fidelity
# regardless of use case.
HIGH_QUALITY_CONTENT_TYPES = {
    "blog",
    "pillar-content",
    "case-study",
    "landing-page",
    "sales-page",
    "product-homepage",
    "brand-page",
    "demo-page",
    "service-page",
}


def _resolve_image_quality(content_type: str) -> str:
    normalized = (content_type or "").strip().lower().replace("_", "-").replace(" ", "-")
    return "medium" if normalized in HIGH_QUALITY_CONTENT_TYPES else "low"


def _decode_image_bytes(response) -> tuple[bytes | None, str | None]:
    """Return (raw_bytes, revised_prompt). gpt-image-2 always returns b64_json."""
    item = response.data[0]
    revised = getattr(item, "revised_prompt", None)
    if item.b64_json:
        return base64.b64decode(item.b64_json), revised
    return None, revised


async def generate_image_standalone(
    prompt: str,
    model: str = DEFAULT_IMAGE_MODEL,
    size: str = "1024x1024",
    quality: str = "low",
) -> str | None:
    """Actual image generation worker. Returns permanent URL or None on failure."""
    print(f"[generate_image_standalone] starting model={model} size={size} quality={quality}")
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    print(f"[generate_image_standalone] prompt={repr(prompt)}...")
    try:
        response = await client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )
        image_bytes, _ = _decode_image_bytes(response)
        if image_bytes is None:
            print("[generate_image_standalone] No image data in response.")
            return None

        from src.utils.storage import storage_service
        if storage_service.available:
            object_name = f"generated-images/{uuid.uuid4()}.png"
            permanent_url = await asyncio.to_thread(
                storage_service.upload_file,
                file_data=image_bytes,
                object_name=object_name,
                content_type="image/png",
            )
            if permanent_url:
                print(f"[generate_image_standalone] uploaded → {permanent_url}")
                return permanent_url

        print("[generate_image_standalone] Storage unavailable or upload failed.")
        return None
    except Exception as e:
        print(f"[generate_image_standalone] Error: {e}")
        return None


def get_tools(counters=None, user_id=None):
    if counters is None:
        counters = {"search": [0]}
    search_count = counters.setdefault("search", [0])
    counters.setdefault("image_task", None)
    counters.setdefault("image_placeholder", None)
    counters.setdefault("search_results", [])

    @tool
    async def search_tool(
        query: str,
    ) -> str:
        """Perform a web search and return top results with snippets."""

        search_count[0] += 1
        current = search_count[0]

        print(
            f"[search_tool] call {current}/{SEARCH_HARD_CAP} "
            f"backend=tavily — query: {query!r}"
        )

        search = TavilySearch(
            k=5,
            include_raw_content=True,
        )

        raw = await search.ainvoke(query)

        # Normalize Tavily response
        if isinstance(raw, dict):
            raw = raw.get("results", [])

        if not isinstance(raw, list):
            print(
                f"[search_tool] call {current} — unexpected Tavily response type: "
                f"{type(raw).__name__}"
            )
            raw = []

        # Keep only dictionary result objects.
        # Prevents "'str' object has no attribute 'get'" errors.
        valid_results = [
            result for result in raw
            if isinstance(result, dict)
        ]

        print(
            f"[search_tool] call {current} — "
            f"raw={len(raw)}, valid={len(valid_results)}"
        )

        if len(valid_results) != len(raw):
            print(
                f"[search_tool] call {current} — "
                f"ignored {len(raw) - len(valid_results)} malformed results"
            )

        if valid_results:
            for i, r in enumerate(valid_results[:5], 1):
                url = r.get("url", "")
                raw_content = r.get("raw_content") or ""
                content = r.get("content") or ""

                print(
                    f"[search_tool] call {current} result {i}: "
                    f"url={url!r} "
                    f"content_chars={len(content)} "
                    f"raw_content_chars={len(raw_content)}"
                )

        if not valid_results:
            print(
                f"[search_tool] call {current} — NO VALID RESULTS, "
                f"returning 0 chars to agent"
            )

            return (
                "NO RESULTS FOUND. "
                "Do NOT invent URLs or statistics. "
                "Write from persona experience only."
            )

        # Ground truth for downstream citation validation
        searched_results = counters.setdefault("search_results", [])

        lines = [
            "SEARCH RESULTS — ONLY CITE THESE EXACT URLs, NO OTHERS:\n"
        ]

        for i, r in enumerate(valid_results[:5], 1):
            url = r.get("url", "")

            if not url:
                continue

            title = r.get("title", "")
            published = r.get("published_date") or ""
            body = r.get("raw_content") or r.get("content", "")
            body = (body or "").strip()[:2000]

            searched_results.append(
                {
                    "url": url,
                    "title": title,
                    "snippet": body,
                }
            )

            lines.append(f"[{i}] URL: {url}")
            if published:
                lines.append(f"    PUBLISHED: {published}")
            lines.append(f"    TITLE: {title}")
            lines.append(f"    CONTENT:\n{body}")
            lines.append("")

        lines.append(
            "USE ONLY THE URLs LISTED ABOVE AS INLINE HYPERLINKS. "
            "DO NOT INVENT OR GUESS ANY URL."
        )

        output = "\n".join(lines)

        print(
            f"[search_tool] call {current} — "
            f"TOTAL chars passed to agent: {len(output)} "
            f"(~{len(output) // 4} tokens est.)"
        )

        print(
            f"[search_tool] call {current} — "
            f"full payload sent to agent:\n{output}\n{'=' * 80}"
        )

        return output

    @tool
    async def generate_image(
        title: str,
        summary: str = "",
        content_type: str = "blog",
        primary_keyword: str = "",
        secondary_keywords: str = "",
        audience: str = "",
        brand_voice: str = "",
        writing_style: str = "",
        search_intent: str = "informational",
        product_name: str = "",
        product_description: str = "",
        model: str = DEFAULT_IMAGE_MODEL,
        size: str = "",
    ) -> str:
        """Generate a featured image via the Image Planning Pipeline.

        Call exactly once per article after searches. Pass article metadata —
        do NOT invent a freeform image prompt. The pipeline plans composition,
        art direction, and the final artist prompt internally.
        Returns immediately — the image is injected automatically after article generation.

        Args:
            title: Article title.
            summary: One-sentence article summary or brief.
            content_type: Any Rext content type (kebab or snake case), e.g.
                blog, how-to-guide, tutorial, checklist, case-study, white-paper,
                explainer, pillar-content, faq, glossary, resource-list,
                comparison, best-tools, alternatives, in-depth-review, pros-cons,
                product-roundup, buying-guide, brand-page, product-homepage,
                feature-overview, documentation, login-guide, contact-us,
                about-us, help-center, landing-page, sales-page, pricing-page,
                signup-page, demo-page, coupon-page, checkout-page, service-page.
            primary_keyword: Focus keyphrase.
            secondary_keywords: Comma-separated secondary keywords.
            audience: Comma-separated target audience labels.
            brand_voice: Brand voice (e.g. premium enterprise, friendly, developer).
            writing_style: Writing style / tone from the outline.
            search_intent: informational, commercial, navigational, or transactional.
            product_name: Optional product name if product-led.
            product_description: Optional short product description.
            size: Optional override — 1024x1024, 1024x1792, or 1792x1024.
                Leave empty to use the pipeline's recommended size.
        """
        composed = compose_image_prompt(
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
        )
        final_prompt = composed.prompt
        resolved_size = size.strip() if size and size.strip() else composed.recommended_size
        resolved_quality = _resolve_image_quality(content_type)

        print(
            f"[generate_image] pipeline composed prompt "
            f"type={content_type} size={resolved_size} quality={resolved_quality} "
            f"prompt={repr(final_prompt)[:120]}"
        )
        counters["image_prompt"] = final_prompt
        counters["image_planning"] = composed.model_dump(mode="json")

        if not settings.AI_IMAGE_GENERATION_ENABLED:
            # Image generation is temporarily disabled (cost control) — the
            # planning pipeline above still ran in full (art direction,
            # composition, alt text, placement); only the paid image-model
            # call is skipped. Reserve a manual-upload placeholder instead —
            # generate_content (which owns `counters`) embeds it in
            # body_markdown so the user can upload a real image from the
            # editor, or dismiss it and publish without one. Do NOT call the
            # image model while this flag is off.
            placeholder_id = str(uuid.uuid4())
            alt_text = f"Featured image for {title}".strip()
            context = (composed.planning_context.visual_story or final_prompt)[:280]
            counters["image_placeholder"] = {
                "placeholder_id": placeholder_id,
                "alt_text": alt_text,
                "context": context,
                "placement": "introduction",
            }
            print(
                f"[generate_image] image generation disabled — reserved manual-upload "
                f"placeholder id={placeholder_id}"
            )
            return json.dumps(
                {
                    "status": (
                        "image generation is disabled right now — a manual-upload "
                        "placeholder was reserved instead, don't call again or wait "
                        "for a result"
                    ),
                    "pipeline": "image_planning",
                }
            )

        task = asyncio.create_task(
            generate_image_standalone(final_prompt, model, resolved_size, resolved_quality)
        )
        counters["image_task"] = task
        return json.dumps(
            {
                "status": "generating now, don't call again or wait for result",
                "pipeline": "image_planning",
                "recommended_size": resolved_size,
            }
        )

    return [search_tool, generate_image]
