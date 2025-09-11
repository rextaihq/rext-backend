from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from src.states.State import AgentState
from src.model.model import search_model
from src.tools.searchTool import get_tools


# Chatbot node function
def web_search(state: AgentState):
    """
    SearchAgent Node Function

    This function takes the current agent state, extracts selected article titles,
    and uses an LLM-based search model to find 5 up-to-date, working article URLs 
    for each title. The found URLs are then attached to the corresponding articles 
    under the 'full_links' key in `selected_articles`.

    Steps:
    1. Extract titles from `selected_articles` in the state.
    2. For each title:
       - Send a prompt to the search model asking for exactly 5 article URLs.
       - Parse the model's response into a Python list of URLs.
       - Append URLs to the matching article in `selected_articles`.
    3. Update the state messages with a success confirmation.
    
    Args:
        state (AgentState): The current agent state containing:
            - selected_articles (list[dict]): Articles with at least a 'title' key.
            - messages (list): Previous conversation messages.

    Returns:
        dict: Updated state with:
            - selected_articles: Articles now containing 'full_links'.
            - messages: Original messages plus a completion message.
    """
    
    print("🔍 Starting web search...")
    selected_articles = state.get("selected_articles", [])

    llm_with_tools = search_model().bind_tools(get_tools())

    for article in selected_articles:
        title = article.get("title", "")
        print(f"   • Processing title: {title}")

        # Build the search request
        system_msg = SystemMessage(
            content=(
                "You are an expert research assistant. Your primary goal is to find "
                "the latest relevant article URLs based on the provided title.\n"
                "- Always return exactly 5 up-to-date, working article URLs.\n"
                "- Do not include titles, summaries, or any explanation.\n"
                "- Only return a valid Python list of strings (URLs).\n\n"
                "Format example:\n"
                "[\n"
                "  \"https://example.com/article1\",\n"
                "  \"https://example.com/article2\",\n"
                "  \"https://example.com/article3\",\n"
                "  \"https://example.com/article4\",\n"
                "  \"https://example.com/article5\"\n"
                "]"
            )
        )
        human_msg = HumanMessage(content=title)

        # Run the LLM search
        response = llm_with_tools.invoke([system_msg, human_msg])
        print(f"      ↳ Model raw output: {response}")

        try:
            print("      ↳ Parsing response...")
            urls = eval(response.content)  # ⚠ Safe here because we control the model format
            if isinstance(urls, list) and all(isinstance(u, str) for u in urls):
                article.setdefault("full_links", []).extend(urls)
                print(f"      ✅ Found URLs: {urls}")
            else:
                raise ValueError("Parsed content is not a valid list of URLs.")
        except Exception as e:
            print(f"      ❌ Error parsing response for '{title}': {e}")
            article.setdefault("full_links", [])

    # Update messages for tool conditions
    updated_messages = state.get("messages", []) + [
        AIMessage(content="Search completed and URLs attached.")
    ]

    return {
        "selected_articles": selected_articles,
        "messages": updated_messages
    }
