import asyncio
import time
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from dotenv import load_dotenv
from openai import AsyncOpenAI
import base64
import json
import os
import uuid

from src.flow.image_generation import compose_image_prompt

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
    t0 = time.perf_counter()
    print(f"[IMAGE] ▶ START model={model} size={size} quality={quality}")
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        response = await client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
        )
        print(f"[IMAGE]   model call done ({time.perf_counter() - t0:.2f}s elapsed)")
        image_bytes, _ = _decode_image_bytes(response)
        if image_bytes is None:
            print(f"[IMAGE] ✗ END ({time.perf_counter() - t0:.2f}s) — no image data in response")
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
                print(f"[IMAGE] ✓ END ({time.perf_counter() - t0:.2f}s) — uploaded -> {permanent_url}")
                return permanent_url

        print(f"[IMAGE] ✗ END ({time.perf_counter() - t0:.2f}s) — storage unavailable or upload failed")
        return None
    except Exception as e:
        print(f"[IMAGE] ✗ END ({time.perf_counter() - t0:.2f}s) — error: {e}")
        return None


def get_tools(counters=None, user_id=None):
    if counters is None:
        counters = {"search": [0]}
    search_count = counters.setdefault("search", [0])
    counters.setdefault("image_task", None)

    @tool
    async def search_tool(
        query: str,
    ) -> str:
        """Perform a web search and return top results with snippets.

        Use this tool for factual questions, current events, research, or up-to-date web info.
        Returns structured results with title, URL, and snippet — cite URLs directly from results.

        Args:
            query: Search query (e.g., "best laptops 2024 review")
        """
        search_count[0] += 1
        current = search_count[0]
        t0 = time.perf_counter()

        print(f"[TOOL search_tool] ▶ START call {current}/{SEARCH_HARD_CAP} query={query!r}")
        search = TavilySearch(k=5, include_raw_content=True)
        raw = await search.ainvoke(query)
        if isinstance(raw, dict):
            raw = raw.get("results", [])
        if not raw:
            print(f"[TOOL search_tool] ✗ END call {current}/{SEARCH_HARD_CAP} ({time.perf_counter() - t0:.2f}s) — no results")
            return "NO RESULTS FOUND. Do NOT invent URLs or statistics. Write from persona experience only."

        # Ground truth for HumanizeMiddleware's fact-source-URL check — only URLs
        # actually shown to the model (the same top-5 slice below) count as real.
        counters.setdefault("searched_urls", set()).update(
            r.get("url") for r in raw[:5] if r.get("url")
        )

        lines = ["SEARCH RESULTS — ONLY CITE THESE EXACT URLs, NO OTHERS:\n"]
        for i, r in enumerate(raw[:5], 1):
            url = r.get("url", "")
            if not url:
                continue
            title = r.get("title", "")
            body = r.get("raw_content") or r.get("content", "")
            body = (body or "").strip()[:2000]
            lines.append(f"[{i}] URL: {url}")
            lines.append(f"    TITLE: {title}")
            lines.append(f"    CONTENT:\n{body}")
            lines.append("")
        lines.append("USE ONLY THE URLs LISTED ABOVE AS INLINE HYPERLINKS. DO NOT INVENT OR GUESS ANY URL.")
        print(f"[TOOL search_tool] ✓ END call {current}/{SEARCH_HARD_CAP} ({time.perf_counter() - t0:.2f}s) — {len(raw)} result(s)")
        return "\n".join(lines)

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
            f"[TOOL generate_image] ▶ START dispatching background task "
            f"type={content_type} size={resolved_size} quality={resolved_quality} "
            f"prompt={repr(final_prompt)[:120]}"
        )
        task = asyncio.create_task(
            generate_image_standalone(final_prompt, model, resolved_size, resolved_quality)
        )
        print("[TOOL generate_image] ✓ END — task dispatched (runs in background, not awaited here)")
        counters["image_task"] = task
        counters["image_prompt"] = final_prompt
        counters["image_planning"] = composed.model_dump(mode="json")
        return json.dumps(
            {
                "status": "generating now, don't call again or wait for result",
                "pipeline": "image_planning",
                "recommended_size": resolved_size,
            }
        )

    return [search_tool, generate_image]
