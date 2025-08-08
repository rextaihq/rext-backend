from langchain_tavily import TavilySearch
from dotenv import load_dotenv
import os
load_dotenv()

def search_tool():
    """
    Initializes and returns a TavilySearch tool configured to retrieve up to 10 basic news results.

    Returns:
        TavilySearch: An instance of the TavilySearch tool with specified parameters.
    """

    """
    Returns a list of all available tools.

    Returns:
    list: A list containing all tool instances.
    """
    try:
        TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')
        tool = TavilySearch(max_results=10,include_answer="basic", topic="news",TAVILY_API_KEY = TAVILY_API_KEY)

        return tool
    except Exception as e:
        print(str(e))
        return {
            "error":str(e)
        }

def get_tools()-> list:
    """
    Return the list of tools
    """

    searchTool  = search_tool()
    return [
        search_tool
    ]

if __name__ == "__main__":
    tool = search_tool()
    results  = tool.invoke("Tell me about open ai")
    print(results)