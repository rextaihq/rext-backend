"""
A run the AI provider can't serve ends with a notice (G75.1, revnix/rext-control#614).

When the provider is unavailable (an empty account, a rate limit, a 5xx, out of reach, the key refused;
src.flow.model.provider_outage) during the outline or the article, the step's catch-all turned it into a
generic error and the run went on, or LangGraph's generic failure ended it. Now those catch-alls let an
outage through. Now the node returns the notice instead, and the graph ends the run at
provider_unavailable, with the same run.failed event and content.error as no_serp_data and topics_failed.
The team is alerted by the model's error hook (G75), once an hour.

Credits: the outline is charged only after it succeeds, so an outline the provider fails costs nothing.
The article's stages are charged before it is written; their refund is F18's (revnix/rext-control#500).
"""

import inspect
import logging
from functools import wraps
from typing import Any, Callable, Dict

from src.flow.model.provider_outage import provider_outage
from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)

PROVIDER_UNAVAILABLE_CODE = "provider_unavailable"
PROVIDER_UNAVAILABLE_NODE = "provider_unavailable"
PROVIDER_UNAVAILABLE_MESSAGE = (
    "The writing service is busy right now, so this run stopped before it finished. "
    "Please try again in a few minutes."
)


def _without_old_notice(state: REXT, result: Any) -> Any:
    """A step that worked clears a notice an earlier attempt on this thread left: `content` deep-merges, so the
    old provider_unavailable code (copied into the step's answer, or left in the state) would route the
    recovered run back to the end. A step's own error code is kept."""
    if not isinstance(result, dict):
        return result
    before = (state.get("content") or {}).get("error_code")
    content = result.get("content") if isinstance(result.get("content"), dict) else None
    after = (content or {}).get("error_code")
    if PROVIDER_UNAVAILABLE_CODE not in (before, after) or after not in (
        None,
        PROVIDER_UNAVAILABLE_CODE,
    ):
        return result
    cleared = dict(content or {})
    cleared["error_code"] = None
    if cleared.get("error", PROVIDER_UNAVAILABLE_MESSAGE) == PROVIDER_UNAVAILABLE_MESSAGE:
        cleared["error"] = None
    return {**result, "content": cleared}


def stop_on_outage(node: Callable) -> Callable:
    """A graph node that, when the AI provider is unavailable, returns the notice instead of raising.

    The node's own catch-all must let an outage through (`generate_outline` and `generate_content` re-raise
    it); one that swallows every error keeps its best-effort behaviour."""

    @wraps(node)
    async def run(state: REXT, *args, **kwargs):
        try:
            result = node(state, *args, **kwargs)
            # A stand-in node (a test's) may be plain; the graph's own are async.
            result = await result if inspect.isawaitable(result) else result
        except Exception as error:
            outage = provider_outage(error)
            if outage is None:
                raise
            logger.warning(
                "%s stopped the run: %s is unavailable (%s)",
                getattr(node, "__name__", "a node"),
                outage.provider,
                outage.kind,
            )
            return {
                "content": {
                    "error": PROVIDER_UNAVAILABLE_MESSAGE,
                    "error_code": PROVIDER_UNAVAILABLE_CODE,
                }
            }
        return _without_old_notice(state, result)

    return run


def unless_outage(next_node: str) -> Callable[[REXT], str]:
    """A router: on to `next_node`, or to the end when the node before returned the outage notice."""

    def route(state: REXT) -> str:
        stopped = (state.get("content") or {}).get("error_code") == PROVIDER_UNAVAILABLE_CODE
        return PROVIDER_UNAVAILABLE_NODE if stopped else next_node

    route.__name__ = f"{next_node}_unless_outage"
    return route


async def provider_unavailable(state: REXT) -> Dict[str, Any]:
    """Terminal node: the notice reaches the user as a run.failed event and as content.error."""
    message = (state.get("content") or {}).get("error") or PROVIDER_UNAVAILABLE_MESSAGE
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()(
            {
                "type": "run",
                "step": "run.failed",
                "error_code": PROVIDER_UNAVAILABLE_CODE,
                "message": message,
            }
        )
    except Exception as exc:  # noqa: BLE001 - reporting never breaks the flow
        logger.warning("provider_unavailable stream emit failed: %s", exc)
    return {"content": {"error": message, "error_code": PROVIDER_UNAVAILABLE_CODE}}
