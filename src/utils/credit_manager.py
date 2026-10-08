"""
Credit manager for pipeline-stage deductions.

Used directly inside LangGraph flow nodes (no FastAPI dependency injection).
DB calls are dispatched to the main FastAPI event loop via run_coroutine_threadsafe
(same pattern as _MainLoopProxy in rext_store.py and _bulk_sync_workspace in outline.py)
because the asyncpg connection pool is bound to the main loop.
Credit events are written to the active LangGraph run stream via get_stream_writer().
"""

from functools import wraps
from typing import Optional
from uuid import UUID

from src.api.database.async_database import get_async_db_context
from src.utils.logger import logger
from src.utils.loop_bridge import MainLoopNotReady

# Credits deducted at each pipeline stage (total = 15 per article)
STAGE_CREDITS: dict[str, int] = {
    "serp_seo": 1,  # SERP + competitor analysis
    "title_generation": 1,  # Title / topic generation
    "generate_outline": 1,  # Outline generation (per call, including regenerations)
    "deep_research": 4,  # Deep web research — Tavily ×6
    "content_drafting": 1,  # Content drafting
    "featured_image": 1,  # Featured image generation
    "humanization": 5,  # Humanization
    "eeat_optimization": 1,  # E-E-A-T optimization
}


class InsufficientCreditsError(Exception):
    def __init__(self, stage: str, required: int, available: int):
        self.stage = stage
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient credits at '{stage}' stage: need {required}, have {available}."
        )


async def _run_on_main_loop(coro):
    """
    Run `coro` on the main FastAPI event loop and await the result, through the one bridge
    (src.utils.loop_bridge): directly on the main loop, dispatched from any other, and never
    on a worker thread's own loop (rext-control#858).
    Propagates exceptions including InsufficientCreditsError.
    """
    from src.utils.loop_bridge import run_on_main_loop

    return await run_on_main_loop(coro)


async def resolve_credit_owner_id(
    db,
    user_id: UUID,
    workspace_id: Optional[UUID] = None,
) -> UUID:
    """
    Resolve the user ID whose subscription/credits should be used.

    Flow:
    Authenticated user -> Active workspace -> Verify active membership -> Workspace owner (workspace.user_id).
    If no workspace_id is provided, returns user_id (personal credits fallback).
    If workspace_id is provided:
      - Validates that workspace exists.
      - If user is the owner (workspace.user_id == user_id), returns workspace.user_id.
      - If user is not the owner, verifies active membership in workspace_members.
      - If verified active member, returns workspace.user_id.
      - If not an active member, raises InsufficientCreditsError to prevent unauthorized credit access.
    """
    if workspace_id is None:
        return user_id

    from sqlalchemy import and_, select

    from src.api.models.workspace_models.workspace_member import WorkspaceMembers
    from src.api.models.workspace_models.workspace_model import WorkspaceModel

    ws_res = await db.execute(select(WorkspaceModel).where(WorkspaceModel.id == workspace_id))
    workspace = ws_res.scalar_one_or_none()
    if not workspace:
        logger.warning(
            "credit_manager: workspace %s not found, rejecting credit resolution for user %s",
            workspace_id,
            user_id,
        )
        raise InsufficientCreditsError(
            stage="workspace_access",
            required=1,
            available=0,
        )

    # If the user is the workspace owner, use their credits directly
    if workspace.user_id == user_id:
        return workspace.user_id

    # Verify active membership
    mem_res = await db.execute(
        select(WorkspaceMembers).where(
            and_(
                WorkspaceMembers.workspace_id == workspace_id,
                WorkspaceMembers.user_id == user_id,
                WorkspaceMembers.status == "active",
            )
        )
    )
    membership = mem_res.scalar_one_or_none()
    if not membership:
        logger.warning(
            "credit_manager: user %s is not an active member of workspace %s",
            user_id,
            workspace_id,
        )
        raise InsufficientCreditsError(
            stage="workspace_access",
            required=1,
            available=0,
        )

    return workspace.user_id


# Below this balance a full article can no longer be generated.
LOW_CREDITS_THRESHOLD = sum(STAGE_CREDITS.values())


async def notify_credit_owner(
    user_id: UUID,
    workspace_id: Optional[UUID],
    *,
    exceeded: bool,
    balance: int,
    required: int = 0,
) -> None:
    """Send the usage-limit notification to whoever owns the credits. Never raises."""
    from src.services.notification_helper import notify_now

    async def _owner() -> UUID:
        async with get_async_db_context() as db:
            return await resolve_credit_owner_id(db, user_id, workspace_id)

    try:
        owner_id = await _run_on_main_loop(_owner())
    except Exception:
        # Not a member / workspace gone: nobody's credits to warn about.
        return

    if exceeded:
        message = (
            f"You've run out of credits: {required} needed, {balance} available. "
            "Upgrade your plan or wait for your monthly reset to keep generating."
        )
    else:
        message = (
            f"You have {balance} credits left, not enough for another full article "
            f"({LOW_CREDITS_THRESHOLD} credits). Upgrade your plan to avoid interruptions."
        )
    await notify_now(
        user_id=owner_id,
        pref_flag="billing_usage_limit_exceeded" if exceeded else "billing_usage_limit_warning",
        message=message,
        payload={"credits_remaining": balance, "credits_required": required},
        workspace_id=workspace_id,
    )


async def _get_balance(uid: UUID, workspace_id: Optional[UUID] = None) -> int:
    """Return current credit balance without deducting. Loop-safe."""

    async def _query() -> int:
        async with get_async_db_context() as db:
            from src.services.usage_tracking_service import UsageTrackingService

            target_uid = await resolve_credit_owner_id(db, uid, workspace_id)
            return await UsageTrackingService(db).get_credit_balance(target_uid)

    return await _run_on_main_loop(_query())


async def can_afford_stage(user_id, stage: str, workspace_id: Optional[UUID] = None) -> bool:
    """
    Whether the credit owner's balance covers `stage` now, without deducting.

    For a stage charged only on delivery (the featured image): the run checks it
    before starting the paid work. True for an unauthenticated run (nothing is
    charged) and when the ids can't be read, as consume_stage_credits skips them.
    """
    if user_id is None:
        return True
    try:
        uid = UUID(str(user_id))
        wid = UUID(str(workspace_id)) if workspace_id else None
    except (ValueError, AttributeError):
        return True
    try:
        return await _get_balance(uid, workspace_id=wid) >= STAGE_CREDITS[stage]
    except InsufficientCreditsError:
        # Not a member of the workspace: nobody's credits to charge.
        return False
    except Exception:
        # The balance can't be read now: the stage's work isn't started, so a run
        # that has paid for its other stages still finishes.
        logger.warning("credit_manager: balance unreadable for %s; treated as unaffordable", stage)
        return False


async def consume_stage_credits(
    user_id, cost: int, stage: str, workspace_id: Optional[UUID] = None
) -> None:
    """
    Deduct `cost` credits for a named pipeline stage from the active workspace owner.

    Loop-safe: dispatches the asyncpg DB call to the main FastAPI event loop
    when called from a LangGraph worker thread (same pattern as _bulk_sync_workspace).
    Raises InsufficientCreditsError if balance is too low or user is not a member.
    Silently skips if user_id is None (unauthenticated runs).
    """
    if user_id is None:
        return

    try:
        uid = UUID(str(user_id))
    except (ValueError, AttributeError):
        logger.warning("credit_manager: invalid user_id %s, skipping deduction", user_id)
        return

    wid: Optional[UUID] = None
    if workspace_id:
        try:
            wid = UUID(str(workspace_id))
        except (ValueError, AttributeError):
            logger.warning("credit_manager: invalid workspace_id %s", workspace_id)

    async def _deduct() -> int:
        async with get_async_db_context() as db:
            from src.services.usage_tracking_service import UsageTrackingService

            target_uid = await resolve_credit_owner_id(db, uid, wid)
            service = UsageTrackingService(db)
            success = await service.consume_credits(target_uid, cost)
            if not success:
                balance = await service.get_credit_balance(target_uid)
                raise InsufficientCreditsError(stage, cost, balance)
            return await service.get_credit_balance(target_uid)

    try:
        balance_after = await _run_on_main_loop(_deduct())
    except InsufficientCreditsError as e:
        if e.stage != "workspace_access":
            await notify_credit_owner(
                uid, wid, exceeded=True, balance=e.available, required=e.required
            )
        raise

    # Warn once, on the deduction that crosses the threshold.
    if balance_after < LOW_CREDITS_THRESHOLD <= balance_after + cost:
        await notify_credit_owner(uid, wid, exceeded=False, balance=balance_after)

    logger.info(
        "Credits deducted: stage=%s cost=%d balance=%d user=%s (workspace=%s)",
        stage,
        cost,
        balance_after,
        uid,
        wid,
    )
    _emit_credit_event(balance_after, stage, cost)


def _emit_credit_event(
    current_credits: int,
    stage: str,
    cost: int,
    *,
    step: str = "credits.updated",
) -> None:
    """
    Write a credit update to the active LangGraph run stream.

    Arrives on the frontend as a `custom` event with `data.type === "credits"`.
    No-op if called outside an active LangGraph run context.
    """
    try:
        from langgraph.config import get_stream_writer

        write = get_stream_writer()
        messages = {
            "credits.updated": f"Credits deducted for stage: {stage}",
            "credits.exhausted": f"Insufficient credits at stage: {stage}",
            "credits.low": f"Low credits warning: {current_credits} remaining",
        }
        write(
            {
                "type": "credits",
                "step": step,
                "current_credits": current_credits,
                "stage": stage,
                "cost": cost,
                "message": messages.get(step, stage),
            }
        )
    except Exception as exc:
        logger.warning("credit stream emit failed: %s", exc)


def deduct_credits(*stages: str, warn_threshold: int = 0):
    """
    Node decorator — pre-checks credits before running the node, then
    deducts per-stage after the node succeeds.

    Pre-flight: balance < total cost → emits credits.exhausted, returns
    an error dict without running the node.

    warn_threshold: balance <= threshold (but still sufficient) →
    emits credits.low before running the node.

    Post-deduction: a stage whose charge is refused (another run spent the
    balance meanwhile) emits credits.exhausted and returns the same error as the
    pre-flight, without the node's result, so the run ends unpaid work there
    instead of handing it to the next stage.

    All DB calls go through _run_on_main_loop to avoid cross-loop asyncpg errors.

    Usage:
        @deduct_credits("generate_outline")
        async def generate_outline(state: REXT): ...

        @deduct_credits("deep_research", "content_drafting", "featured_image", warn_threshold=15)
        async def generate_content(state: REXT): ...
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(state):
            serp_payload = state.get("serp_payload") or {}
            user_id = serp_payload.get("user_id") or state.get("user_id")
            workspace_id = serp_payload.get("workspace_id") or state.get("workspace_id")
            uid: "UUID | None" = None
            wid: "UUID | None" = None

            if user_id:
                try:
                    uid = UUID(str(user_id))
                except (ValueError, AttributeError):
                    logger.warning("credit_manager: invalid user_id %s", user_id)

            if workspace_id:
                try:
                    wid = UUID(str(workspace_id))
                except (ValueError, AttributeError):
                    logger.warning("credit_manager: invalid workspace_id %s", workspace_id)

            # Pre-flight credit check
            if uid is not None:
                try:
                    total_cost = sum(STAGE_CREDITS[s] for s in stages)
                    balance = await _get_balance(uid, wid)

                    if balance < total_cost:
                        logger.warning(
                            "Pre-flight credit check failed: need %d for %s, have %d (user=%s, workspace=%s)",
                            total_cost,
                            stages,
                            balance,
                            uid,
                            wid,
                        )
                        _emit_credit_event(balance, stages[0], total_cost, step="credits.exhausted")
                        await notify_credit_owner(
                            uid, wid, exceeded=True, balance=balance, required=total_cost
                        )
                        return {
                            "content": {
                                "error": (
                                    f"Insufficient credits: need {total_cost} for this stage, "
                                    f"have {balance}. Please upgrade your plan."
                                ),
                                "error_code": "insufficient_credits",
                            }
                        }

                    if warn_threshold > 0 and balance <= warn_threshold:
                        logger.warning(
                            "Low credits: %d remaining for user=%s (threshold=%d, workspace=%s)",
                            balance,
                            uid,
                            warn_threshold,
                            wid,
                        )
                        _emit_credit_event(balance, stages[0], 0, step="credits.low")

                except InsufficientCreditsError:
                    raise
                except MainLoopNotReady:
                    # No way to the database from this job's thread: the charge after the
                    # stage could not be made either, so its paid work does not run.
                    raise
                except Exception as exc:
                    logger.warning("Credit pre-flight check failed: %s — proceeding", exc)

            result = await fn(state)
            content = result.get("content") if isinstance(result, dict) else None
            if content and not content.get("error"):
                if uid is not None:
                    for stage in stages:
                        try:
                            await consume_stage_credits(
                                user_id, STAGE_CREDITS[stage], stage, workspace_id=wid
                            )
                        except InsufficientCreditsError as e:
                            logger.warning(
                                "Out of credits at stage '%s': need %d, have %d (user=%s, workspace=%s)",
                                e.stage,
                                e.required,
                                e.available,
                                user_id,
                                wid,
                            )
                            try:
                                _emit_credit_event(
                                    e.available, e.stage, e.required, step="credits.exhausted"
                                )
                            except Exception:
                                pass
                            return {
                                "content": {
                                    "error": (
                                        f"Insufficient credits: need {e.required} for this stage, "
                                        f"have {e.available}. Please upgrade your plan."
                                    ),
                                    "error_code": "insufficient_credits",
                                }
                            }
            return result

        return wrapper

    return decorator
