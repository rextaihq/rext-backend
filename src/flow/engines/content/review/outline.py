import logging
from langgraph.graph import END
from langgraph.types import interrupt, Command
from src.flow.states.wrext import WREXT

logger = logging.getLogger(__name__)

def review_outline(state: WREXT):
    """
    Interrupts for human approval of the generated outline.
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
        "instructions": "Please approve or reject the generated outline. If rejecting, provide a reason.",
        # "action": ""
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
        return {
            "content":{
                **content_state,
                "outline":{
                    **outline_dict,
                    "rejected_reason": "",
                    "status": "approved"
                },
            }
        }
    
    if action == "reject":
        # If reason wasn't provided in the first interrupt, ask for it
        reject_reason = review_data.get("reason")
        if not reject_reason:
            reject_response = interrupt({
                "type": "outline_reject",
                "instructions": "Please provide a reason for rejecting the outline."
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