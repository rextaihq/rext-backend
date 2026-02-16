import logging
from typing import Dict, Any
from src.flow.states.rext import REXT
from src.flow.model.structure.topics import SEOTopics
from src.flow.model.llm_manager import load_model
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage
from src.flow.model.structure.intent_suggession import INTENT_TO_CONTENT_TYPES

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
    # Check for upstream errors — skip processing if prior node failed
    if content_state.get("error"):
        logger.warning(
            "Skipping content type selection due to upstream error: %s",
            content_state["error"],
        )
        return {"content": content_state}
    selected_topic = content_state.get("selected_topic", "")
    
    # get the intent from the state - aggregate intent distribution across all competitors
    competitors = state.get("competitors", [])
    
    # Aggregate intent distributions from all competitors
    aggregated_intent: Dict[str, int] = {}
    for competitor in competitors:
        intent_distribution = competitor.get("intent_distribution", {})
        for intent, count in intent_distribution.items():
            aggregated_intent[intent] = aggregated_intent.get(intent, 0) + count
    
    # Find the intent with maximum distribution
    max_intent = None
    if aggregated_intent:
        max_intent = max(aggregated_intent, key=aggregated_intent.get)

    if not selected_topic:
        logger.warning("No selected topic found in state")
        return state

    # show the topic and ask the user to select the content type
    selected_content_type = interrupt({
        "instruction": "Select a content type for your topic",
        "topic": selected_topic,
        "content_types": INTENT_TO_CONTENT_TYPES.get(max_intent, []),
        "type": "content_type"
    })

    # Save the selected content type to the state
    content_state["content_type"] = selected_content_type
    state["content"] = content_state
    
    logger.info(f"Content type selected: {selected_content_type}")
    
    return state