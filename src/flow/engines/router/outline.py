from src.flow.states.rext import REXT
import logging
logger = logging.getLogger(__name__)

def outline_router(state: REXT) -> str:
    """
    Routes the workflow based on outline approval status.
    
    Returns:
        - "generate_content" if outline is explicitly approved
        - "generate_outline" to continue editing
    """
    content_state = state.get("content", {})
    outline_state = content_state.get("outline", {})
    outline_status = outline_state.get("status", "")

    if outline_status == "approved":
        logger.info("Outline approved, proceeding to content generation")
        return "generate_content"

    logger.info("Outline not approved; re-running outline generation")
    return "generate_outline"
