import logging
from uuid import UUID

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


async def library_router(state: REXT) -> str:
    """Route the workflow based on whether it is a library request.

    A start from the keyword Library (is_library) loads the item it names
    (load_library_item: its stored research, then a fresh SERP, without the
    keyword gate). Anything else follows the full path from SERP analysis.

    Also gates the whole run on credits before any billed stage runs: if the
    user can't afford a full article, route straight to END instead of
    burning SERP/outline/etc. calls before failing midway. If the balance
    can't be read, the run doesn't start either (credit_check_failed).
    """
    serp_payload = state.get("serp_payload", {})
    user_id = serp_payload.get("user_id") or state.get("user_id")
    workspace_id = serp_payload.get("workspace_id") or state.get("workspace_id")

    if user_id:
        from src.utils.credit_manager import (
            STAGE_CREDITS,
            InsufficientCreditsError,
            _emit_credit_event,
            _get_balance,
            notify_credit_owner,
        )

        # The start check fails closed: a run whose credits can't be read doesn't
        # start, since parallel runs would otherwise spend past an unread balance.
        total_cost = sum(STAGE_CREDITS.values())
        try:
            uid = UUID(str(user_id))
            wid = UUID(str(workspace_id)) if workspace_id else None
            balance = await _get_balance(uid, workspace_id=wid)
        except InsufficientCreditsError:
            # Not a member of the workspace whose credits would pay.
            logger.warning("Blocking run: the workspace's credits don't cover this caller")
            return "insufficient_credits"
        except Exception as exc:
            # The class only: a database error's text can carry the query's parameters.
            logger.warning("Blocking run: the credit check failed (%s)", type(exc).__name__)
            return "credit_check_failed"

        if balance < total_cost:
            logger.warning(
                "Blocking run: need %d credits for a full article, have %d", total_cost, balance
            )
            _emit_credit_event(balance, "pipeline_start", total_cost, step="credits.exhausted")
            await notify_credit_owner(uid, wid, exceeded=True, balance=balance, required=total_cost)
            return "insufficient_credits"

        # A Library start announces itself once its item has loaded
        # (load_library_item): a refused one never started.
        if not serp_payload.get("is_library"):
            try:
                from src.services.notification_helper import notify_now

                await notify_now(
                    user_id=uid,
                    pref_flag="gen_started",
                    message=f'Generating content for "{serp_payload.get("query") or "your keyword"}".',
                    payload={"query": serp_payload.get("query")},
                    workspace_id=wid,
                )
            except Exception as exc:
                logger.warning("library_router: the start notification failed: %s", exc)

    is_library = serp_payload.get("is_library", False)

    if is_library:
        logger.info("Library start: loading the item's stored research")
        return "load_library_item"

    return "serp_engine"
