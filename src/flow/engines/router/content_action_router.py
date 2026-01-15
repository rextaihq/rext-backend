import logging
from langgraph.graph import END
from src.flow.states.wrext import WREXT

logger = logging.getLogger(__name__)

def content_action_router(state: WREXT) -> str:
    """
    Routes to the appropriate handler node based on user's selected action.
    
    Returns:
        - "handle_publish" if action is "publish"
        - "handle_edit" if action is "edit"
        - "handle_save" if action is "save"
        - END if no valid action found
    """
    content_state = state.get("content", {})
    action = content_state.get("action", "").lower()
    
    logger.info(f"Routing based on action: {action}")
    
    if action == "publish":
        return "handle_publish"
    elif action == "edit":
        return "handle_edit"
    elif action == "save":
        return "handle_save"
    else:
        logger.warning(f"Unknown action '{action}', routing to END")
        return END
