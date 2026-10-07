import logging

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def keyword_router(state: REXT) -> str:
    """Route after the keyword interrupt based on keyword/country changes.

    Returns "NO_SERP" when the SERP had no results (keyword_recommendation
    then returns without a gate and sets an error), which ends the run;
    "SERP_ENGINE" to re-run the whole analysis (SERP, competitors,
    SEO metrics, recommendations) if the user picked a different keyword or
    country; or "END" to proceed to content generation. Re-analysis is
    deliberately uncapped: every pass pauses on the keyword
    interrupt for a human answer, so the user decides when to stop
    (and each pass bills its own SERP credits).
    """
    seo_result = state.get("seo_result", {})
    keyword_recs = seo_result.get("keyword_recommendations", {})
    is_changed = keyword_recs.get("is_changed", False)

    if keyword_recs.get("titles_unpaid"):
        logger.info("The title charge was refused, ending the run")
        return "INSUFFICIENT"

    if keyword_recs.get("error"):
        logger.info("No SERP results for the keyword, ending the run")
        return "NO_SERP"

    if is_changed:
        logger.info("Keyword or country changed, re-running SERP and SEO analysis")
        return "SERP_ENGINE"

    return "END"
