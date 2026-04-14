from langchain_core.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.tools.ddg_search import DuckDuckGoSearchRun
from dotenv import load_dotenv
from openai import OpenAI
import json
import os

load_dotenv()

@tool
def search_tool(query: str) -> str:
    """Perform a web search using DuckDuckGo and return top 5 results with snippets.

    Use this tool for factual questions, current events, research, or up-to-date web info.
    Returns structured results with title, URL, and snippet for citation.

    Args:
        query: Search query (e.g., "best laptops 2024 review")
    """
    search = DuckDuckGoSearchRun(
        max_results=5,
        search_depth="advanced",
    )
    results = search.run(query)
    return json.dumps(results, indent=2)


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
    # Create the OpenAI client
    # Assumes OPENAI_API_KEY is set in your environment variables
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size,
            quality="standard",  # or "hd"
        )
        
        # Extract the URL from the response
        image_url = response.data[0].url
        return image_url

    except Exception as e:
        print(f"Error generating image: {e}")
        return None


def get_tools():
    return [search_tool, generate_image]
