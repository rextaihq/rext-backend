import logging
from langgraph.graph import END
from langgraph.types import interrupt, Command
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

def review_outline(state: REXT):
    """Interrupt workflow for human approval of the generated outline.

    Presents the outline to the user via LangGraph's ``interrupt()``
    mechanism. Handles approve/reject actions, optionally prompting
    for a rejection reason if not provided.

    Args:
        state: REXT state containing ``content.outline``.

    Returns:
        dict: State update with ``content.outline.status`` set to
        ``"approved"`` or ``"rejected"`` with reason.
    """
    content_state = state.get("content", {})
    outline_dict = content_state.get("outline", {})
    
    # if not outline_dict:
    #     logger.error("No outline found in state to review")
    #     return Command(goto="generate_outline")

    # 1. Interrupt for human approval
    logger.info("Interrupting for human review of outline...")
    review_result = interrupt({
        "type": "outline_review",
        "data": outline_dict,
        "instruction": "Please approve or reject the generated outline. If rejecting, provide a reason.",
    })
    
    # 2. Handle review result
    if isinstance(review_result, str):
        action = review_result.lower()
        review_data = {}
    elif isinstance(review_result, dict):
        action = review_result.get("action", "").lower()
        review_data = review_result
    else:
        action = ""
        review_data = {}
    # 
    if action == "approve":
        logger.info("Outline approved by human")
        
        # Extract updated tone and audience if provided
        updated_tone = review_data.get("tone")
        updated_audience = review_data.get("target_audience")
        
        outline_update = {
            **outline_dict,
            "rejected_reason": "",
            "status": "approved"
        }
        
        if updated_tone:
            outline_update["tone"] = updated_tone
        if updated_audience:
            outline_update["target_audience"] = updated_audience

        logger.info(f"Tone: {updated_tone}, Audience: {updated_audience} approved by human")

        return {
            "content":{
                **content_state,
                "outline": outline_update,
            }
        }
    
    if action == "reject":
        # If reason wasn't provided in the first interrupt, ask for it
        reject_reason = review_data.get("reason")
        if not reject_reason:
            reject_response = interrupt({
                "type": "outline_reject",
                "instruction": "Please provide a reason for rejecting the outline."
            })
            if isinstance(reject_response, str):
                reject_reason = reject_response
            elif isinstance(reject_response, dict):
                reject_reason = reject_response.get("reason", "No reason provided")
            else:
                reject_reason = "No reason provided"
        
        logger.info(f"Outline rejected: {reject_reason}")
        return  {
            "content":{
                **content_state,
                "outline":{
                    **outline_dict,
                    "rejected_reason": reject_reason,
                    "status": "rejected"
                },
            }
        }
    
    return {}