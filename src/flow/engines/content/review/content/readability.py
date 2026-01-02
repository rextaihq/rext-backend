import logging
import textstat
from src.flow.states.wrext import WREXT

logger = logging.getLogger(__name__)

def calculate_readability(state: WREXT):
    """
    Calculates readability metrics for the generated content.
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

        # Ensure review exists
        review = content_state.get("review", {})
        review["readability_metrics"] = metrics

        logger.info(f"Readability metrics calculated: {metrics}")

        return {
            "content": {
                **content_state,
                "review": review
            }
        }
    except Exception as e:
        logger.exception(f"Error calculating readability: {str(e)}")
        return {"content": {**content_state}}