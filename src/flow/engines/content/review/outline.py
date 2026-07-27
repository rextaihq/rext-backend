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
            "internal_links": outline_dict.get("internal_links", []),
            "brand_voice_promotion": outline_dict.get("brand_voice_promotion"),
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

        # Extract updated tone, audience, and word count if provided
        updated_tone = review_data.get("tone")
        updated_audience = review_data.get("target_audience")
        updated_word_count = review_data.get("target_word_count")
        if updated_word_count is not None:
            try:
                updated_word_count = int(updated_word_count)
            except (TypeError, ValueError):
                logger.warning(f"Ignoring invalid target_word_count: {updated_word_count}")
                updated_word_count = None
            else:
                if not (500 <= updated_word_count <= 5000):
                    logger.warning(f"Ignoring out-of-range target_word_count: {updated_word_count}")
                    updated_word_count = None

        # Use user-selected internal links if provided, else keep all
        selected_links = review_data.get("selected_internal_links")
        if selected_links is not None:
            internal_links = selected_links
            logger.info(f"User selected {len(internal_links)} internal link(s)")
        else:
            internal_links = outline_dict.get("internal_links", [])

        # Brand promotion decision — user can override the recommendation
        promote_brand: bool = review_data.get(
            "promote_brand",
            bool(
                (outline_dict.get("brand_voice_promotion") or {}).get("recommended", False)
            ),
        )
        logger.info(f"[BrandPromo] promote_brand={promote_brand}")

        outline_update = {
            **outline_dict,
            "internal_links": internal_links,
            "promote_brand": promote_brand,
            "rejected_reason": "",
            "status": "approved",
        }

        if updated_tone:
            outline_update["tone"] = updated_tone
        if updated_audience:
            outline_update["target_audience"] = updated_audience
        if updated_word_count is not None:
            outline_update["target_word_count"] = updated_word_count

        logger.info(
            "Tone: %s, Audience: %s, Target Word Count: %s approved by human",
            updated_tone,
            updated_audience,
            updated_word_count,
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
