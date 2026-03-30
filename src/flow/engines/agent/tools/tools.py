from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from dotenv import load_dotenv
import json
import os

load_dotenv()

@tool
def search_tool(query: str) -> str:
    """Perform a web search using Tavily and return top 5 results with snippets.

    Use this tool for factual questions, current events, research, or up-to-date web info.
    Returns structured results with title, URL, and snippet for citation.

    Args:
        query: Search query (e.g., "best laptops 2024 review")
    """
    search = TavilySearchResults(
        max_results=5,
        search_depth="advanced",
        api_key=os.getenv("TAVILY_API_KEY"),
    )
    results = search.run(query)
    return json.dumps(results, indent=2)

@tool
def search_image_tool(query: str) -> str:
    """Search for a real, valid image URL to embed in the article.

    Returns ONLY a direct image URL (e.g. https://images.unsplash.com/...).
    Embed it in markdown as: ![descriptive alt text](returned_url)
    NEVER invent or guess URLs — only use what this tool returns.
    If the tool returns NO_IMAGE_FOUND, skip the image entirely.

    Args:
        query: Image description (e.g., "AI automation robots manufacturing 2024")
    """
    try:
        search = TavilySearchResults(
            max_results=5,
            search_depth="basic",
            include_images=True,
            api_key=os.getenv("TAVILY_API_KEY"),
        )
        response = search.run(query)

        return json.dumps(response, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


def get_tools():
    return [search_tool, search_image_tool]
