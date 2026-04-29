import logging
from src.flow.states.rext import REXT
from langgraph.types import interrupt
from src.flow.model.structure.intent_suggestion import INTENT_TO_CONTENT_TYPES

logger = logging.getLogger(__name__)


def content_type(state: REXT) -> REXT:
    logger.info("Starting content type selection")

    content_state = state.get("content", {})

    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})
    logger.info(f"serp_backlinks: {serp_backlinks}")

    search_intent = serp_backlinks.get("main_intent", "informational")
    if search_intent == "unknown":
        search_intent = "informational"
    else:
        search_intent = search_intent

    # show the intent and ask the user to select the content type
    selected_content_type = interrupt({
        "instruction": "Select a content type",
        "search_intent": search_intent,
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