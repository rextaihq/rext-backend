import os
import requests
from langchain_core.messages import HumanMessage
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_ollama import ChatOllama
from langchain_core.tools import BaseTool


llm = ChatOllama(model="gpt-oss:120b-cloud", temperature=0)

from langchain.agents import create_agent  # v1 API
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


class UnsplashImageSearchTool(BaseTool):
    name: str = "unsplash_image_search"
    description: str = "Search for images on Unsplash. Returns images with markdown embeds and direct URLs."

    def _run(self, query: str) -> str:
        access_key = os.getenv("UNSPLASH_ACCESS_KEY")
        if not access_key:
            return "Error: UNSPLASH_ACCESS_KEY not found in environment variables."

        url = f"https://api.unsplash.com/search/photos?query={query}&per_page=5"
        headers = {"Authorization": f"Client-ID {access_key}"}

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
                return f"No images found for '{query}'."

            lines = []
            for img in results:
                image_url = img["urls"]["regular"]
                alt_text = img.get("alt_description") or img.get("description") or query
                photographer = img["user"]["name"]
                photo_page = img["links"]["html"]
                lines.append(
                    f"![{alt_text}]({image_url})\n"
                    f"URL: {image_url}\n"
                    f"Photo by [{photographer}]({photo_page}) on Unsplash"
                )
            return "\n\n".join(lines)
        except Exception as e:
            return f"Error fetching images from Unsplash: {str(e)}"


def get_tools():
    search = DuckDuckGoSearchResults(output_format="list")
    unsplash = UnsplashImageSearchTool()

    return [search, unsplash]