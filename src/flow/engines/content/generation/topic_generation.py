import logging
from typing import Dict, Any
from src.flow.states.rext import REXT
from src.flow.model.structure.topics import SEOTopics
from src.flow.model.llm_manager import topic_generation_model
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime, timezone
logger = logging.getLogger(__name__)


async def topic_generation(state: REXT) -> Dict[str, Any]:
    """
    Generate SEO topics based on the user's query.
    
    Flow:
    1. Generate 5 SEO topics using LLM
    2. Interrupt to show topics to user for selection
    3. Save selected topic to state
    
    Uses the LLM to generate 5 relevant SEO topics for content creation.
    """
    logger.info("Starting topic generation")

    # Get the normalized query from SERP results or fallback to input payload
    normalized_result = state.get("serp_normalized", {})
    
    # Check for upstream errors — skip processing if prior node failed
    if normalized_result and normalized_result.get("error"):
        logger.warning(
            "Skipping topic generation due to upstream error: %s",
            normalized_result["error"],
        )
        return {"content": {"topics": [], "selected_topic": ""}}

    query = normalized_result.get("query")
    
    if not query:
        serp_payload = state.get("serp_payload", {})
        query = serp_payload.get("query", "")

    
    if not query:
        logger.warning("No query found in serp_normalized")
        return {"content": {"topics": [], "selected_topic": ""}}

    # Load the model with structured output
    model = topic_generation_model().with_structured_output(SEOTopics)
    current_year = datetime.now(timezone.utc).year
    # Use a LIST of messages, not a SET
    messages = [
    SystemMessage(
        content=(
            f"You are a SEO expert. Generate a high quality list of 5 topics related to the given topic. "
            f"Focus on topics that rank well in search engines, provide value to readers, and are relevant in {current_year}. "
            f"Prefer trends, latest strategies, and current best practices."
        )
    ),
    HumanMessage(
        content=f"Generate 5 topics for: {query} in {current_year}"
    )
]
    
    results: SEOTopics = await model.ainvoke(messages)
    topics = results.topics
    
    logger.info(f"Generated {len(topics)} topics")   
    
    # ========================================
    # INTERRUPT FOR USER SELECTION
    # ========================================
    user_selection = interrupt({
        "instruction": "Select a topic for your content",
        "type": "topic",
        "topics": topics,
    })
    
    logger.info(f"Raw user_selection from interrupt: {user_selection}")
    
    # Handle user selection (can be index, string, or dict)
    selected_topic = ""
    
    if isinstance(user_selection, int):
        # User selected by index (1-5)
        if 1 <= user_selection <= len(topics):
            selected_topic = topics[user_selection - 1]
    elif isinstance(user_selection, str):
        # User typed the topic directly or selected from list
        selected_topic = user_selection.strip()
        # If they typed a number as string
        if selected_topic.isdigit():
            idx = int(selected_topic)
            if 1 <= idx <= len(topics):
                selected_topic = topics[idx - 1]
    elif isinstance(user_selection, dict):
        selected_topic = (user_selection.get("Selected Topic") or "")
        if isinstance(selected_topic, int):
            if 1 <= selected_topic <= len(topics):
                selected_topic = topics[selected_topic - 1]
    
    # Fallback to first topic if selection is empty or invalid
    if not selected_topic:
        logger.warning(f"Failed to parse a valid topic from: {user_selection}. Falling back to topic 1.")
        selected_topic = topics[0] if topics else ""
    
    logger.info(f"User selected topic: {selected_topic}")
    
    return {
        "content": {
            "topics": topics,
            "selected_topic": selected_topic
        }
    }