import logging
from src.flow.states.wrext import WREXT

logger = logging.getLogger(__name__)

def handle_save(state: WREXT):
    """
    Handle the 'save' action - saves content as draft and completes the flow.
    """
    logger.info("Handling save action - saving content as draft")
    
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})
    
    return {
        "content": {
            **content_state,
            "final_content": {
                **final_content,
                "status": "draft"
            },
            "status": "completed"
        }
    }
