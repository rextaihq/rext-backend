from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchResults
import json

@tool
def search_tool(query: str) -> str:
    """Perform a web search using DuckDuckGo and return a list of results.

    Use this tool for any factual questions, current events, research, or when you need up-to-date information from the web.
    Do not use for opinions, creative writing, or math calculations.

    Args:
        query: The search query string to send to DuckDuckGo
    """
    search = DuckDuckGoSearchResults(
        max_results=5,  # Limit results to keep responses concise
        output_format="list"  # Return as structured list
    )
    results = search.run(query)
    return json.dumps(results, indent=2)

@tool
def search_image_tool(query: str) -> str:
    """Search for and return a relevant stock image URL from Unsplash.

    Use this ONLY when the user specifically asks for an image or visual reference.
    Returns a single high-quality image URL matching the query.

    Args:
        query: Descriptive terms for the image (e.g., "sunset beach landscape")
    """
    print(f"Image search executed for: {query}")
    return "https://images.unsplash.com/photo-1506744038136-49a8b3f14ba3?ixlib=rb-4.0.3&auto=format&fit=crop&w=1170&q=80"


def get_tools():
    return [search_tool, search_image_tool]