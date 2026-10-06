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
    burning SERP/outline/etc. calls before failing midway.
    """
    serp_payload = state.get("serp_payload", {})
    user_id = serp_payload.get("user_id") or state.get("user_id")
    workspace_id = serp_payload.get("workspace_id") or state.get("workspace_id")

    if user_id:
        from src.utils.credit_manager import (
            STAGE_CREDITS,
            _emit_credit_event,
            _get_balance,
            notify_credit_owner,
        )

        try:
            uid = UUID(str(user_id))
            wid = UUID(str(workspace_id)) if workspace_id else None
            total_cost = sum(STAGE_CREDITS.values())
            balance = await _get_balance(uid, workspace_id=wid)
            if balance < total_cost:
                logger.warning(
                    "Blocking run: need %d credits for a full article, have %d (user=%s, workspace=%s)",
                    total_cost,
                    balance,
                    uid,
                    wid,
                )
                _emit_credit_event(balance, "pipeline_start", total_cost, step="credits.exhausted")
                await notify_credit_owner(
                    uid, wid, exceeded=True, balance=balance, required=total_cost
                )
                return "insufficient_credits"

            from src.services.notification_helper import notify_now

            # A Library start announces itself once its item has loaded
            # (load_library_item): a refused one never started.
            if serp_payload.get("is_library"):
                return "load_library_item"

            await notify_now(
                user_id=uid,
                pref_flag="gen_started",
                message=f'Generating content for "{serp_payload.get("query") or "your topic"}".',
                payload={"query": serp_payload.get("query")},
                workspace_id=wid,
            )
        except (ValueError, AttributeError):
            logger.warning(
                "library_router: invalid user_id %s or workspace_id %s", user_id, workspace_id
            )
        except Exception as exc:
            logger.warning("library_router credit check failed: %s — proceeding", exc)

    is_library = serp_payload.get("is_library", False)

    if is_library:
        logger.info("Library start: loading the item's stored research")
        return "load_library_item"

    return "serp_engine"
