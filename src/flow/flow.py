from src.flow.states.content_state import ContentState
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableLambda

# --- Nodes ---
from src.flow.nodes.info.get_topics import fetch_topic
from src.flow.nodes.info.get_user import fetch_user
from src.flow.nodes.info.get_workspace import fetch_workspace
from src.flow.nodes.get_context.web_context import web_context
from src.flow.nodes.get_context.workspace_context import workspace_context
from src.flow.nodes.scrapping.scrapper import scrape_content
from src.flow.nodes.reranker.reranker import rerank_documents
from src.flow.nodes.blog_generation.generate_blog import generate_blog
from src.flow.nodes.content.save_content import save_content


def create_workflow() -> RunnableLambda[ContentState, ContentState]:
    """
    Build the full blog generation workflow.

    Steps:
        1. Fetch user, workspace, and topic data (parallel)
        2. Gather knowledge & web context (parallel)
        3. Scrape supporting content from discovered URLs
        4. Rerank documents for relevance using Cohere
        5. Generate blog article with AI
        6. Save generated content to database
    """
    workflow = StateGraph(ContentState)

    # --- Register nodes ---
    workflow.add_node("FetchUser", fetch_user)
    workflow.add_node("FetchWorkspace", fetch_workspace)
    workflow.add_node("FetchTopic", fetch_topic)
    workflow.add_node("KnowledgeContext", workspace_context)
    workflow.add_node("WebContext", web_context)
    workflow.add_node("ScrapeContent", scrape_content)
    workflow.add_node("RerankContent", rerank_documents)
    workflow.add_node("BlogGeneration", generate_blog)
    workflow.add_node("SaveContent", save_content)

    # --- Define workflow edges ---
    workflow.add_edge(START,"FetchUser")
    workflow.add_edge(START,"FetchWorkspace")
    workflow.add_edge(START, "FetchTopic")

    workflow.add_edge("FetchUser","WebContext")
    workflow.add_edge("FetchWorkspace","WebContext")
    workflow.add_edge("FetchTopic","WebContext")

    workflow.add_edge("FetchUser","KnowledgeContext")
    workflow.add_edge("FetchWorkspace","KnowledgeContext")
    workflow.add_edge("FetchTopic","KnowledgeContext")

    workflow.add_edge("KnowledgeContext", "ScrapeContent")
    workflow.add_edge("WebContext", "ScrapeContent")

    # Complete workflow - rerank, generate, save
    workflow.add_edge("ScrapeContent", "RerankContent")
    workflow.add_edge("RerankContent", "BlogGeneration")
    workflow.add_edge("BlogGeneration", "SaveContent")
    workflow.add_edge("SaveContent", END)

    return workflow