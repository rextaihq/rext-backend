import asyncio
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage
from langchain_tavily import TavilySearch
from langgraph.types import Command
from langgraph.constants import END
from dotenv import load_dotenv
from openai import AsyncOpenAI
from typing import Annotated
import base64
import json
import os
import uuid

load_dotenv()

SEARCH_HARD_CAP = 6
IMAGE_HARD_CAP = 1


def _decode_image_bytes(response) -> tuple[bytes | None, str | None]:
    """Return (raw_bytes, revised_prompt). gpt-image-2 always returns b64_json."""
    item = response.data[0]
    revised = getattr(item, "revised_prompt", None)
    if item.b64_json:
        return base64.b64decode(item.b64_json), revised
    return None, revised


def get_tools(counters=None):
    if counters is None:
        counters = {"search": [0], "image": [0]}
    search_count = counters["search"]
    image_count = counters.setdefault("image", [0])

    @tool
    async def search_tool(
        query: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command | str:
        """Perform a web search and return top results with snippets.

        Use this tool for factual questions, current events, research, or up-to-date web info.
        Returns structured results with title, URL, and snippet — cite URLs directly from results.

        Args:
            query: Search query (e.g., "best laptops 2024 review")
        """
        # Check and increment before any await — atomic in asyncio's cooperative model
        if search_count[0] >= SEARCH_HARD_CAP:
            print(f"[search_tool] Hard cap {SEARCH_HARD_CAP} reached — FORCING STOP for query: {query!r}")
            return Command(
                goto=END,
                update={
                    "messages": [
                        ToolMessage(
                            content=(
                                "HARD STOP: search cap reached (6/6). "
                                "You have gathered sufficient evidence. "
                                "Do NOT call search_tool or generate_image again. "
                                "Proceed IMMEDIATELY to writing the final article now with information gathered from prior searches and their references."
                            ),
                            tool_call_id=tool_call_id,
                        )
                    ]
                },
            )
        search_count[0] += 1
        current = search_count[0]

        print(f"[search_tool] call {current}/{SEARCH_HARD_CAP} backend=tavily — query: {query!r}")
        search = TavilySearch(k=5, include_raw_content=True)
        raw = await search.ainvoke(query)
        if isinstance(raw, dict):
            raw = raw.get("results", [])
        if not raw:
            return "NO RESULTS FOUND. Do NOT invent URLs or statistics. Write from persona experience only."

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
        return "\n".join(lines)

    @tool
    async def generate_image(
        prompt: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
        model: str = "gpt-image-2-2026-04-21",
        size: str = "1024x1024",
    ) -> Command | str:
        """Generate an image and return a permanent URL.

        Call this tool exactly once per article. Do not call again after a URL is returned.

        Args:
            prompt: Descriptive prompt for the image.
            size: Resolution — 1024x1024, 1024x1792, or 1792x1024.
        """
        # Check before any await — atomic in asyncio's cooperative model
        if image_count[0] >= IMAGE_HARD_CAP:
            print(f"[generate_image] Hard cap {IMAGE_HARD_CAP} reached — FORCING STOP.")
            return Command(
                goto=END,
                update={
                    "messages": [
                        ToolMessage(
                            content=(
                                "HARD STOP: image generation cap reached. "
                                "No more tool calls are allowed. "
                                "Output the final structured article immediately using only data already gathered with references."
                            ),
                            tool_call_id=tool_call_id,
                        )
                    ]
                },
            )

        print(f"[generate_image] attempt model={model} size={size}")

        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        try:
            response = await client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size=size,
                quality="low",
            )

            image_bytes, revised_prompt = _decode_image_bytes(response)

            if image_bytes is None:
                print("[generate_image] No image data in response.")
                return json.dumps({"error": "Image generation returned no data."})

            try:
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
                        image_count[0] += 1
                        return json.dumps({
                            "url": permanent_url,
                            "revised_prompt": revised_prompt or prompt
                        })

                print("[generate_image] Storage unavailable or failed — skipping image embedding.")
                image_count[0] += 1
                return json.dumps({
                    "url": "SKIPPED",
                    "revised_prompt": revised_prompt or prompt,
                    "info": "Storage unavailable. Do NOT embed an image in this article. Proceed silently with text only."
                })
            except Exception as upload_err:
                print(f"[generate_image] Storage upload failed: {upload_err}")

            image_count[0] += 1
            return json.dumps({
                "url": "SKIPPED",
                "revised_prompt": revised_prompt or prompt,
                "info": "An unexpected error occurred during storage. Do NOT embed an image. Proceed with text only."
            })

        except Exception as e:
            print(f"[generate_image] Error: {e}")
            return json.dumps({"error": str(e)})

    return [search_tool, generate_image]
