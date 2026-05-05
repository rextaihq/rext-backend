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
FETCH_HARD_CAP = 3


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


def get_tools():
    import threading
    search_count = [0]
    fetch_count = [0]
    lock = threading.Lock()

    @tool
    def search_tool(query: str) -> str:
        """Perform a web search and return top results with snippets.

        Use this tool for factual questions, current events, research, or up-to-date web info.
        Returns structured results with title, URL, and snippet for citation.
        After getting results, use fetch_page on the most promising URLs to read full content.

        Args:
            query: Search query (e.g., "best laptops 2024 review")
        """
        with lock:
            if search_count[0] >= SEARCH_HARD_CAP:
                print(f"[search_tool] Hard cap {SEARCH_HARD_CAP} reached — blocking call for query: {query!r}")
                return json.dumps({"error": f"Search cap of {SEARCH_HARD_CAP} reached. Stop searching and write the article now."})
            search_count[0] += 1
            current = search_count[0]
        searxng_host = os.getenv("SEARXNG_HOST")
        backend = f"searxng({searxng_host})" if searxng_host else "duckduckgo"
        print(f"[search_tool] call {current}/{SEARCH_HARD_CAP} backend={backend} — query: {query!r}")
        if searxng_host:
            from langchain_community.utilities import SearxSearchWrapper

            wrapper = SearxSearchWrapper(searx_host=searxng_host)
            raw = wrapper.results(query, num_results=10)
            results = [
                {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
                for r in raw if r.get("link", "")
            ][:5]
            if not results:
                return json.dumps({"error": "No results found. Do NOT invent URLs. Write from your own expertise instead."})
        else:
            return json.dumps({"error": "No SEARXNG_HOST configured. Search unavailable."})
        return json.dumps(results, indent=2)

    @tool
    def fetch_page(url: str) -> str:
        """Fetch and extract the full readable text content of a specific article or page.

        Use this after search_tool to read the full content of a promising result.
        Only fetch URLs that point to a specific article, blog post, study, or page — NOT homepages or root domains.
        A good URL has a meaningful path, e.g. /blog/how-to-grow-instagram or /articles/case-study-results.
        A bad URL is just a domain root: forbes.com, techcrunch.com, harvard.edu — these return no useful content.
        Only cite URLs that you have successfully fetched — this proves the link is real and accessible.
        Cap: 3 calls total.

        Args:
            url: Full URL to a specific article or page (must be from search_tool results, must have a meaningful path)
        """
        from urllib.parse import urlparse

        with lock:
            if fetch_count[0] >= FETCH_HARD_CAP:
                print(f"[fetch_page] Hard cap {FETCH_HARD_CAP} reached — blocking fetch for url: {url!r}")
                return json.dumps({"error": f"Fetch cap of {FETCH_HARD_CAP} reached. Use what you have."})

            # Reject homepage/root URLs before spending a fetch call
            parsed = urlparse(url)
            path = parsed.path.rstrip("/")
            if not path or path in ("", "/"):
                print(f"[fetch_page] Rejected root/homepage URL: {url!r}")
                return json.dumps({
                    "error": "Rejected: this is a homepage or root domain URL with no specific content path. "
                             "Choose a URL that points to a specific article, study, or blog post instead.",
                    "url": url,
                })

            fetch_count[0] += 1
            current = fetch_count[0]

        print(f"[fetch_page] call {current}/{FETCH_HARD_CAP} — url: {url!r}")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"
            }
            response = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            response.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
                tag.decompose()

            # Prefer article/main body; fall back to body
            container = soup.find("article") or soup.find("main") or soup.find("body")
            if not container:
                return json.dumps({"error": "No readable content found", "url": url})

            # Extract text from meaningful tags only
            chunks = []
            for el in container.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 40:  # skip trivial fragments
                    chunks.append(text)

            full_text = "\n\n".join(chunks)
            # Cap at 4000 chars — enough for the LLM to extract facts, quotes, and examples
            truncated = full_text[:4000]
            if len(full_text) > 4000:
                truncated += "\n\n[...content truncated...]"

            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            return json.dumps({
                "url": url,
                "title": title,
                "content": truncated,
            }, indent=2)

        except httpx.HTTPStatusError as e:
            return json.dumps({"error": f"HTTP {e.response.status_code}", "url": url})
        except Exception as e:
            return json.dumps({"error": str(e), "url": url})

    return [search_tool, fetch_page, generate_image]
