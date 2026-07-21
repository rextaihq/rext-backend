import logging
from uuid import UUID

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

MAX_KEYWORD_ITERATIONS = 3


async def library_router(state: REXT) -> str:
    """Route the workflow based on whether it is a library request.

    If is_library is True, skip SERP and SEO analysis and go straight to content generation.
    Otherwise, follow the full path starting with SERP analysis.

    Also gates the whole run on credits before any billed stage runs: if the
    user can't afford a full article, route straight to END instead of
    burning SERP/outline/etc. calls before failing midway.
    """
    serp_payload = state.get("serp_payload", {})
    user_id = serp_payload.get("user_id")

    if user_id:
        from src.utils.credit_manager import STAGE_CREDITS, _emit_credit_event, _get_balance

        try:
            uid = UUID(str(user_id))
            total_cost = sum(STAGE_CREDITS.values())
            balance = await _get_balance(uid)
            if balance < total_cost:
                logger.warning(
                    "Blocking run: need %d credits for a full article, have %d (user=%s)",
                    total_cost, balance, uid,
                )
                _emit_credit_event(balance, "pipeline_start", total_cost, step="credits.exhausted")
                return "insufficient_credits"
        except (ValueError, AttributeError):
            logger.warning("library_router: invalid user_id %s", user_id)
        except Exception as exc:
            logger.warning("library_router credit check failed: %s — proceeding", exc)

    is_library = serp_payload.get("is_library", False)

    if is_library:
        logger.info("Skip SERP and SEO ENGINE - Jumping to content_engine")
        return "content_engine"

    return "serp_engine"