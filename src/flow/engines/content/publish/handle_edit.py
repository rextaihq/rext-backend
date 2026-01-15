import logging
from src.flow.states.wrext import WREXT

logger = logging.getLogger(__name__)

def handle_edit(state: WREXT):
    """
    Handle the 'edit' action - signals frontend to enable inline editing.
    Content remains in editing status.
    """
    logger.info("Handling edit action - signaling frontend for inline editing")
    
    content_state = state.get("content", {})
    
    return {
        "content": {
            **content_state,
            "status": "editing"
        }
    }
