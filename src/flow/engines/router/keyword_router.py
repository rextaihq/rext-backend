import logging

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def keyword_router(state: REXT) -> str:
    """Route after the keyword interrupt based on keyword/country changes.

    Returns "SERP_ENGINE" to re-run the whole analysis (SERP, competitors,
    SEO metrics, recommendations) if the user picked a different keyword or
    country, or "END" to proceed to content generation. Re-analysis is
    deliberately uncapped: every pass pauses on the keyword
    interrupt for a human answer, so the user decides when to stop
    (and each pass bills its own SERP credits).
    """
    seo_result = state.get("seo_result", {})
    keyword_recs = seo_result.get("keyword_recommendations", {})
    is_changed = keyword_recs.get("is_changed", False)

    if is_changed:
        logger.info("Keyword or country changed, re-running SERP and SEO analysis")
        return "SERP_ENGINE"

    return "END"
