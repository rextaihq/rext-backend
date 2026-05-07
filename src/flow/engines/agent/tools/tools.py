from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from dotenv import load_dotenv
from openai import OpenAI
import json
import os
import uuid
import httpx

load_dotenv()

SEARCH_HARD_CAP = 8


@tool
def generate_image(prompt: str, model: str = "dall-e-3", size: str = "1024x1024"):
    """
    Generates an image using OpenAI's DALL-E model and returns the URL.

    Args:
        prompt (str): The text description of the image.
        model (str): The model to use (default "dall-e-3").
        size (str): Image resolution (1024x1024, 1024x1792, or 1792x1024).

    Returns:
        str: The URL of the generated image.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size,
            quality="standard",
        )

        # OpenAI returns a temporary Azure SAS URL that expires in ~2 hours.
        # Download and re-upload to our own storage for a permanent URL.
        temp_url = response.data[0].url

        try:
            from src.utils.storage import storage_service
            from src.api.config import get_settings
            # Only persist when MINIO_PUBLIC_URL is set — otherwise get_file_url
            # returns a presigned URL (1 h expiry) which is shorter than the
            # original OpenAI SAS URL (~2 h) and would make the problem worse.
            if storage_service.available and get_settings().MINIO_PUBLIC_URL:
                image_response = httpx.get(temp_url, timeout=30)
                image_response.raise_for_status()
                object_name = f"generated-images/{uuid.uuid4()}.png"
                permanent_url = storage_service.upload_file(
                    file_data=image_response.content,
                    object_name=object_name,
                    content_type="image/png",
                )
                if permanent_url:
                    return permanent_url
        except Exception as upload_err:
            print(f"Failed to persist image to storage, falling back to temp URL: {upload_err}")

        return temp_url

    except Exception as e:
        print(f"Error generating image: {e}")
        return None


def get_tools(counters=None):
    import threading
    if counters is None:
        counters = {"search": [0], "lock": threading.Lock()}
    search_count = counters["search"]
    lock = counters["lock"]

    @tool
    def search_tool(query: str) -> str:
        """Perform a web search and return top results with snippets.

        Use this tool for factual questions, current events, research, or up-to-date web info.
        Returns structured results with title, URL, and snippet — cite URLs directly from results.

        Args:
            query: Search query (e.g., "best laptops 2024 review")
        """
        with lock:
            if search_count[0] >= SEARCH_HARD_CAP:
                print(f"[search_tool] Hard cap {SEARCH_HARD_CAP} reached — blocking call for query: {query!r}")
                return json.dumps({"error": (
                    f"Search cap of {SEARCH_HARD_CAP} reached. "
                    "You now have all the evidence you need. "
                    "Review the facts, statistics, and URLs collected from your previous searches. "
                    "Write the article using ONLY those facts and ONLY those exact URLs as inline links. "
                    "Do NOT invent any URL, name, statistic, or outcome not present in your prior search results. "
                    "For any section with no search evidence, write a first-person persona observation instead."
                )})
            search_count[0] += 1
            current = search_count[0]
        print(f"[search_tool] call {current}/{SEARCH_HARD_CAP} backend=tavily — query: {query!r}")
        search = TavilySearchResults(k=5, include_raw_content=True)
        raw = search.invoke(query)
        if not raw:
            return "NO RESULTS FOUND. Do NOT invent URLs or statistics. Write from persona experience only."

        lines = ["SEARCH RESULTS — ONLY CITE THESE EXACT URLs, NO OTHERS:\n"]
        for i, r in enumerate(raw[:5], 1):
            url = r.get("url", "")
            if not url:
                continue
            title = r.get("title", "")
            # Prefer raw_content (full article text) over short snippet
            body = r.get("raw_content") or r.get("content", "")
            body = (body or "").strip()[:2000]
            lines.append(f"[{i}] URL: {url}")
            lines.append(f"    TITLE: {title}")
            lines.append(f"    CONTENT:\n{body}")
            lines.append("")
        lines.append("USE ONLY THE URLs LISTED ABOVE AS INLINE HYPERLINKS. DO NOT INVENT OR GUESS ANY URL.")
        return "\n".join(lines)

    return [search_tool, generate_image]