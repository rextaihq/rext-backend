import logging
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def keyword_router(state: REXT) -> str:
    """Route the SEO engine based on keyword recommendation changes.

    Returns "SEO_ENGINE" to re-run analysis if keywords changed,
    or "END" to proceed to content generation. Re-analysis is
    deliberately uncapped: every pass pauses on the keyword
    interrupt for a human answer, so the user decides when to stop
    (and each pass bills its own SERP credits).
    """
    seo_result = state.get("seo_result", {})
    keyword_recs = seo_result.get("keyword_recommendations", {})
    is_changed = keyword_recs.get("is_changed", False)

    if is_changed:
        logger.info("Keyword changed, re-running SEO analysis")
        return "SEO_ENGINE"

    return "END"
