import logging
from langgraph.types import interrupt
from src.flow.states.wrext import WREXT

logger = logging.getLogger(__name__)

def review_action(state: WREXT):
    """
    Interrupts after content review to present three action options:
    - Publish: Mark content as published and end flow
    - Edit: Allow frontend to handle inline editing
    - Save: Save content as draft and end flow
    """
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})
    review = content_state.get("review", {})
    
    if not final_content:
        logger.warning("No final content found for review action")
        return {"content": content_state}
    
    # Prepare interrupt payload with review data
    logger.info("Interrupting for content review action...")
    user_action = interrupt({
        "type": "content_review_action",
        "data": {
            "final_content": final_content,
            "review": review
        },
        "instruction": "Content review complete. Please choose an action: Publish, Edit, or Save.",
        "actions": ["publish", "edit", "save"]
    })
    
    # Handle the user's action selection
    if isinstance(user_action, str):
        action = user_action.lower()
    elif isinstance(user_action, dict):
        action = user_action.get("action", "").lower()
    else:
        logger.warning("Invalid action received, defaulting to save")
        action = "save"
    
    logger.info(f"User selected action: {action}")
    
    return {
        "content": {
            **content_state,
            "action": action
        }
    }
