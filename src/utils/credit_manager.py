"""
Credit manager for pipeline-stage deductions.

Used directly inside LangGraph flow nodes (no FastAPI dependency injection).
Each call creates its own DB session via get_async_db_context.
"""
from functools import wraps
from uuid import UUID

from src.api.database.async_database import get_async_db_context
from src.utils.logger import logger


# Credits deducted at each pipeline stage (total = 15 per article)
STAGE_CREDITS: dict[str, int] = {
    "serp_seo": 1,            # SERP + competitor analysis
    "keyword_research": 1,    # Keyword & topic research
    "generate_outline": 1,    # Outline generation (per call, including regenerations)
    "deep_research": 4,       # Deep web research — Tavily ×6
    "content_drafting": 1,    # Content drafting (gpt-4o-mini)
    "featured_image": 1,      # Featured image generation
    "humanization": 5,        # Humanization
    "eeat_optimization": 1,   # E-E-A-T optimization
}


class InsufficientCreditsError(Exception):
    def __init__(self, stage: str, required: int, available: int):
        self.stage = stage
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient credits at '{stage}' stage: need {required}, have {available}."
        )


async def consume_stage_credits(user_id, cost: int, stage: str) -> None:
    """
    Deduct `cost` credits from user's subscription for a named pipeline stage.

    Creates its own DB session — safe to call from LangGraph nodes.
    Raises InsufficientCreditsError if balance is too low.
    Silently skips if user_id is None (non-authenticated runs).
    """
    if user_id is None:
        return

    try:
        uid = UUID(str(user_id))
    except (ValueError, AttributeError):
        logger.warning("credit_manager: invalid user_id %s, skipping deduction", user_id)
        return

    async with get_async_db_context() as db:
        from src.services.usage_tracking_service import UsageTrackingService
        service = UsageTrackingService(db)
        success = await service.consume_credits(uid, cost)
        if not success:
            balance = await service.get_credit_balance(uid)
            raise InsufficientCreditsError(stage, cost, balance)

    logger.debug("Credits deducted: stage=%s cost=%d user=%s", stage, cost, uid)


def deduct_credits(*stages: str):
    """
    Node decorator — deducts stage credits after a node function returns successfully.

    Skips deduction when the node returns an error dict or empty result, so failed
    nodes never burn credits.

    Usage:
        @deduct_credits("generate_outline")
        async def generate_outline(state: REXT): ...

        @deduct_credits("deep_research", "content_drafting", "featured_image")
        async def generate_content(state: REXT): ...
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(state):
            result = await fn(state)
            content = result.get("content") if isinstance(result, dict) else None
            if content and not content.get("error"):
                user_id = (state.get("serp_payload") or {}).get("user_id")
                for stage in stages:
                    await consume_stage_credits(user_id, STAGE_CREDITS[stage], stage)
            return result
        return wrapper
    return decorator
