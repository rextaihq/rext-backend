import logging
from typing import Dict, Any
from src.flow.states.wrext import WREXT
from src.flow.model.structure.topics import SEOTopics
from src.flow.model.llm_manager import load_model
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)


def content_type(state: WREXT) -> WREXT:
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
    selected_topic = content_state.get("selected_topic", "")
    
    if not selected_topic:
        logger.warning("No selected topic found in state")
        return state

    # show the topic and ask the user to select the content type
    selected_content_type = interrupt({
        "instruction": "Select a content type for your topic",
        "topic": selected_topic,
        "content_types": ["article", "blog", "report", "whitepaper"]
    })

    # Save the selected content type to the state
    content_state["content_type"] = selected_content_type
    state["content"] = content_state
    
    logger.info(f"Content type selected: {selected_content_type}")
    
    return state