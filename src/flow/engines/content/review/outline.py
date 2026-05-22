import logging

from langgraph.types import interrupt

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
    outline_dict = dict(content_state.get("outline", {}) or {})
    seo_result = state.get("seo_result", {})
    keyword_clusters = seo_result.get("keyword_clusters", [])

    # Ensure cluster mapping is available in the outline dict for the frontend
    cluster_heading_map = content_state.get("cluster_heading_map") or outline_dict.get(
        "cluster_heading_map",
        {},
    )
    logger.info(f"Cluster heading map for outline review: {cluster_heading_map}")
    if cluster_heading_map:
        outline_dict["cluster_heading_map"] = cluster_heading_map

    # 1. Interrupt for human approval
    logger.info("Interrupting for human review of outline...")
    review_result = interrupt(
        {
            "type": "outline_review",
            "data": outline_dict,
            "clusters": keyword_clusters,
            "instruction": (
                "Please approve or reject the generated outline. "
                "If rejecting, provide a reason."
            ),
        }
    )

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
            "status": "approved",
        }

        if updated_tone:
            outline_update["tone"] = updated_tone
        if updated_audience:
            outline_update["target_audience"] = updated_audience

        logger.info(
            "Tone: %s, Audience: %s approved by human",
            updated_tone,
            updated_audience,
        )

        return {
            "content": {
                **content_state,
                "outline": outline_update,
            }
        }

    if action == "reject":
        # If reason wasn't provided in the first interrupt, ask for it
        reject_reason = review_data.get("reason")
        if not reject_reason:
            reject_response = interrupt(
                {
                    "type": "outline_reject",
                    "instruction": "Please provide a reason for rejecting the outline.",
                }
            )
            if isinstance(reject_response, str):
                reject_reason = reject_response
            elif isinstance(reject_response, dict):
                reject_reason = reject_response.get("reason", "No reason provided")
            else:
                reject_reason = "No reason provided"

        logger.info(f"Outline rejected: {reject_reason}")
        return {
            "content": {
                **content_state,
                "outline": {
                    **outline_dict,
                    "rejected_reason": reject_reason,
                    "status": "rejected",
                },
            }
        }

    return {}
