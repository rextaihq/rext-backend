import logging
import textstat
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

def calculate_readability(state: REXT):
    """Calculate readability metrics for generated content.

    Uses the ``textstat`` library to compute Flesch Reading Ease,
    Flesch-Kincaid Grade, Gunning Fog, SMOG, ARI, Coleman-Liau,
    and Dale-Chall scores on the body markdown content.

    Args:
        state: REXT state containing ``content.final_content.body_markdown``.

    Returns:
        dict: State update with ``content.review.readability_metrics``
        populated, or unchanged content state on failure.
    """
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})
    body_content = final_content.get("body_markdown", "")

    if not body_content:
        logger.warning("No content found to calculate readability")
        return {"content": {**content_state}}

    try:
        metrics = {
            "flesch_reading_ease": textstat.flesch_reading_ease(body_content),
            "flesch_kincaid_grade": textstat.flesch_kincaid_grade(body_content),
            "gunning_fog_index": textstat.gunning_fog(body_content),
            "smog_index": textstat.smog_index(body_content),
            "automated_readability_index": textstat.automated_readability_index(body_content),
            "coleman_liau_index": textstat.coleman_liau_index(body_content),
            "dale_chall_score": textstat.dale_chall_readability_score(body_content),
        }

        logger.info(f"Readability metrics calculated: {metrics}")

        # Return only the update delta for deep merging
        return {
            "content": {
                "review": {
                    "readability_metrics": metrics
                }
            }
        }
    except Exception as e:
        logger.exception(f"Error calculating readability: {str(e)}")
        return {"content": {**content_state}}