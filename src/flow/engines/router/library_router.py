import logging
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

MAX_KEYWORD_ITERATIONS = 3


def library_router(state: REXT) -> str:
    """Route the workflow based on whether it is a library request.

    If is_library is True, skip SERP and SEO analysis and go straight to content generation.
    Otherwise, follow the full path starting with SERP analysis.
    """
    serp_payload = state.get("serp_payload", {})
    is_library = serp_payload.get("is_library", False)

    if is_library:
        logger.info("Skip SERP and SEO ENGINE - Jumping to content_engine")
        return "content_engine"

    return "serp_engine"