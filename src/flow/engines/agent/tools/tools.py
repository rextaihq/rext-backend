from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from dotenv import load_dotenv
from openai import OpenAI
import json
import os
import uuid
import httpx

load_dotenv()

SEARCH_HARD_CAP = 6


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
                return json.dumps({"error": f"Search cap of {SEARCH_HARD_CAP} reached. Stop searching and write the article now."})
            search_count[0] += 1
            current = search_count[0]
        print(f"[search_tool] call {current}/{SEARCH_HARD_CAP} backend=tavily — query: {query!r}")
        search = TavilySearchResults(k=5)
        raw = search.invoke(query)
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in raw if r.get("url", "")
        ][:5]
        if not results:
            return json.dumps({"error": "No results found. Do NOT invent URLs. Write from your own expertise instead."})
        return json.dumps(results, indent=2)

    return [search_tool, generate_image]
