import logging
from typing import Dict, Any
from src.flow.states.rext import REXT
from src.flow.model.structure.topics import SEOTopics
from src.flow.model.llm_manager import load_model
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

    # Get the normalized query
    normalized_result = state.get("serp_normalized", {})
    query = normalized_result.get("query", "")
    
    if not query:
        logger.warning("No query found in serp_normalized")
        return {"content": {"topics": [], "selected_topic": ""}}

    # Load the model with structured output
    model = load_model().with_structured_output(SEOTopics)
    current_year = datetime.now().year
    # Use a LIST of messages, not a SET
    messages = [
    SystemMessage(
        content=(
            f"You are a SEO expert. Generate a high quality list of 5 SEO topics related to the given topic. "
            f"Focus on topics that rank well in search engines, provide value to readers, and are relevant in {current_year}. "
            f"Prefer trends, latest strategies, and current best practices."
        )
    ),
    HumanMessage(
        content=f"Generate 5 SEO topics for: {query} in {current_year}"
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
    
    # Handle user selection (can be index, string, or dict)
    selected_topic = ""
    
    if isinstance(user_selection, int):
        # User selected by index (1-5)
        if 1 <= user_selection <= len(topics):
            selected_topic = topics[user_selection - 1]
        else:
            selected_topic = topics[0]  # Default to first topic
    elif isinstance(user_selection, str):
        # User typed the topic directly or selected from list
        selected_topic = user_selection.strip()
        # If they typed a number as string
        if selected_topic.isdigit():
            idx = int(selected_topic)
            if 1 <= idx <= len(topics):
                selected_topic = topics[idx - 1]
    elif isinstance(user_selection, dict):
        # User returned a dict with selection
        selected_topic = user_selection.get("selected_topic", "") or user_selection.get("topic", "")
    
    # Fallback to first topic if selection is empty
    if not selected_topic:
        selected_topic = topics[0] if topics else ""
    
    logger.info(f"User selected topic: {selected_topic}")
    
    return {
        "content": {
            "topics": topics,
            "selected_topic": selected_topic
        }
    }