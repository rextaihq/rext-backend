import logging
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

MAX_KEYWORD_ITERATIONS = 3


def keyword_router(state: REXT) -> str:
    """Route the SEO engine based on keyword recommendation changes.

    Returns "SEO_ENGINE" to re-run analysis if keywords changed,
    or "END" to proceed to content generation. Enforces a maximum
    iteration limit to prevent infinite loops.
    """
    seo_result = state.get("seo_result", {})
    iteration_count = seo_result.get("keyword_iteration_count", 0)

    if iteration_count >= MAX_KEYWORD_ITERATIONS:
        logger.warning(
            "Max keyword iterations (%d) reached, forcing workflow to proceed",
            MAX_KEYWORD_ITERATIONS,
        )
        return "END"

    keyword_recs = seo_result.get("keyword_recommendations", {})
    is_changed = keyword_recs.get("is_changed", False)

    if is_changed:
        logger.info(
            "Keywords changed (iteration %d/%d), re-running SEO analysis",
            iteration_count + 1,
            MAX_KEYWORD_ITERATIONS,
        )
        return "SEO_ENGINE"

    return "END"