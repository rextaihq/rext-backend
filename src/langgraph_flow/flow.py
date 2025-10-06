from src.langgraph_flow.states.content_state import ContentState
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda

# --- Nodes ---
from src.langgraph_flow.nodes.get_topics import fetch_topic
from src.langgraph_flow.nodes.get_context.web_context import web_context
from src.langgraph_flow.nodes.get_context.workspace_context import workspace_context
from src.langgraph_flow.nodes.scrapping.scrapper import scrape_content
from src.langgraph_flow.nodes.reranker.reranker import rerank_documents
from src.langgraph_flow.nodes.blog_generation.generate_blog import generate_blog


def create_workflow() -> RunnableLambda[ContentState, ContentState]:
    """
    Build the full blog generation workflow.

    Steps:
        1. Fetch topic
        2. Gather knowledge & web context
        3. Scrape supporting content
        4. Rerank documents for relevance
        5. Generate blog article
    """
    workflow = StateGraph(ContentState)

    # --- Register nodes ---
    workflow.add_node("FetchTopic", fetch_topic)
    workflow.add_node("KnowledgeContext", workspace_context)
    workflow.add_node("WebContext", web_context)
    workflow.add_node("ScrapeContent", scrape_content)
    workflow.add_node("RerankContent", rerank_documents)
    workflow.add_node("BlogGeneration", generate_blog)

    # --- Define workflow edges ---
    workflow.add_edge(START, "FetchTopic")

    workflow.add_edge("FetchTopic", "KnowledgeContext")
    workflow.add_edge("FetchTopic", "WebContext")

    workflow.add_edge("KnowledgeContext", "ScrapeContent")
    workflow.add_edge("WebContext", "ScrapeContent")

    workflow.add_edge("ScrapeContent", "RerankContent")
    workflow.add_edge("RerankContent", "BlogGeneration")

    workflow.add_edge("BlogGeneration", END)

    return workflow