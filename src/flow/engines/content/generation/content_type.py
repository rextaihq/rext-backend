import logging
from typing import Dict, Any
from src.flow.states.rext import REXT
from src.flow.model.structure.topics import SEOTopics
from src.flow.model.llm_manager import load_model
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage
from src.flow.model.structure.intent_suggestion import INTENT_TO_CONTENT_TYPES

from src.flow.utils.intent_utils import get_consensus_intent

logger = logging.getLogger(__name__)


def content_type(state: REXT) -> REXT:
    """
    Generate SEO topics based on the user's query.
    
    Flow:
    1. Interrupt to show topics to user for selection
    2. Save selected topic to state
    
    Uses the LLM to generate 5 relevant SEO topics for content creation.
    """
    logger.info("Starting topic generation")
    
    # get the selected topic from the state
    content_state = state.get("content", {})
    competitors = state.get("competitors", [])

    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})
    logger.info(f"serp_backlinks: {serp_backlinks}")

    # Use consensus intent (API + Competitors) for better accuracy
    api_intent = serp_backlinks.get("main_intent")
    search_intent = get_consensus_intent(api_intent, competitors)

    # Check for upstream errors — skip processing if prior node failed
    if content_state.get("error"):
        logger.warning(
            "Skipping content type selection due to upstream error: %s",
            content_state["error"],
        )
        return {"content": content_state}
    selected_topic = content_state.get("selected_topic", "")

    if not selected_topic:
        logger.warning("No selected topic found in state")
        return state

    # show the topic and ask the user to select the content type
    selected_content_type = interrupt({
        "instruction": "Select a content type for your topic",
        "topic": selected_topic,
        "content_types": INTENT_TO_CONTENT_TYPES.get(search_intent.lower(), []),
        "type": "content_type"
    })

    # Handle user selection (can be string or dict)
    final_selection = ""
    if isinstance(selected_content_type, str):
        final_selection = selected_content_type
    elif isinstance(selected_content_type, dict):
        final_selection = (
            selected_content_type.get("content_type") or 
            selected_content_type.get("Selected Content Type") or 
            ""
        )
    
    # Save the selected content type to the state
    content_state["content_type"] = final_selection or "article"
    state["content"] = content_state
    
    logger.info(f"Content type selected: {content_state['content_type']}")
    
    return state