import logging
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def keyword_router(state: REXT) -> str:
    """Route based on whether keyword recommendations have changed.

    Uses safe dictionary access to prevent KeyError when state
    is incomplete or partially populated.
    """
    seo_result = state.get("seo_result", {})
    keyword_recs = seo_result.get("keyword_recommendations", {})
    is_changed = keyword_recs.get("is_changed", False)

    if is_changed:
        return "SEO_ENGINE"
    return "END"