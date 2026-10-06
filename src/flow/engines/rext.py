import logging

from langgraph.graph import END, START, StateGraph

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def create_rext_engine():
    """Create and return the compiled REXT workflow graph.

    Returns a cached singleton — the graph is compiled once and reused
    for all subsequent calls. Pass a checkpointer for state persistence
    when invoking the graph directly (outside the LangGraph Platform).
    """

    from src.flow.engines.content.content_engine import create_content_engine
    from src.flow.engines.router.keyword_router import keyword_router
    from src.flow.engines.router.library_router import library_router
    from src.flow.engines.seo.library_item import library_item_router, load_library_item
    from src.flow.engines.seo.seo_engine import create_seo_engine
    from src.flow.engines.serp.serp_engine import create_serp_engine

    flow = StateGraph(REXT)

    flow.add_node("serp_engine", create_serp_engine())
    flow.add_node("seo_engine", create_seo_engine())
    flow.add_node("content_engine", create_content_engine())
    flow.add_node("insufficient_credits", _insufficient_credits)
    flow.add_node("no_serp_data", _no_serp_data)
    flow.add_node("load_library_item", load_library_item)

    flow.add_conditional_edges(
        START,
        library_router,
        {
            "serp_engine": "serp_engine",
            "load_library_item": "load_library_item",
            "insufficient_credits": "insufficient_credits",
        },
    )

    # A Library start: the item's stored research, then a fresh SERP; an item
    # that is not in the caller's Library ends the run (E17, rext-control#368).
    flow.add_conditional_edges(
        "load_library_item",
        library_item_router,
        {"serp_engine": "serp_engine", "end": END},
    )

    # A search with no organic result ends the run here, before seo_engine
    # charges the serp_seo credit or calls the keyword overview (founder,
    # 2026-10-05: such a run is not charged). A Library start already has its
    # keyword research, so it goes from the SERP straight to the content steps,
    # without the keyword gate.
    flow.add_conditional_edges(
        "serp_engine",
        _after_serp,
        {
            "seo_engine": "seo_engine",
            "content_engine": "content_engine",
            "no_serp_data": "no_serp_data",
        },
    )
    # A changed keyword or country must re-run the SERP engine too, otherwise the
    # recommendations/competitors of the previous analysis would be reused.
    flow.add_conditional_edges(
        "seo_engine",
        keyword_router,
        {"SERP_ENGINE": "serp_engine", "END": "content_engine", "NO_SERP": "no_serp_data"},
    )
    flow.add_edge("content_engine", END)
    flow.add_edge("insufficient_credits", END)
    flow.add_edge("no_serp_data", END)

    return flow.compile()


async def _insufficient_credits(state: REXT) -> dict:
    """Terminal node for runs blocked by the credit gate in library_router."""
    # This returns a successful response carrying an error payload, so no
    # exception handler ever sees it and the event was recorded nowhere. The
    # equivalent limit on workspaces raises and is logged as a warning; the
    # same condition reaching the user through a different mechanism should
    # not decide whether an operator can see it. Nothing is broken here -- the
    # plan is working as designed -- so it is a warning, not an error.
    try:
        from src.services.monitoring_service import MonitoringService

        await MonitoringService.persist_error_log(
            api_severity="medium",
            message="Content generation blocked: insufficient credits",
            source="flow rext.insufficient_credits",
            path="/flow/rext/insufficient_credits",
            metadata={
                "error_code": "insufficient_credits",
                "workspace_id": str(state.get("workspace_id") or ""),
                "blocked_at": "library_router credit gate",
            },
        )
    except Exception:  # noqa: BLE001 - reporting never breaks the flow
        pass

    return {
        "content": {
            "error": "Insufficient credits to generate content. Please upgrade your plan.",
            "error_code": "insufficient_credits",
        }
    }


# What the user reads when a run ends for want of search results, by the
# SERP fetch's serp_status.
def _after_serp(state: REXT) -> str:
    """After the SERP: none to work from, a Library start's content steps, or the keyword step."""
    from src.flow.engines.serp.normalization import has_organic_results

    if not has_organic_results(state):
        return "no_serp_data"
    if (state.get("serp_payload") or {}).get("is_library"):
        return "content_engine"
    return "seo_engine"


NO_SERP_MESSAGES = {
    "no_results": (
        "No search results were found for this keyword. "
        "Check the spelling or try a broader keyword."
    ),
    "lookup_failed": (
        "Search results could not be loaded for this keyword. Please try again in a few minutes."
    ),
}


async def _no_serp_data(state: REXT) -> dict:
    """Terminal node for runs whose keyword has no SERP results to work from.

    The message reaches the user twice: as a custom stream event (type
    "run", step "run.failed") for the generation view that is streaming, and
    as content.error in the thread state, which the dock's status poll reads.
    """
    serp_status = (state.get("serp_result") or {}).get("serp_status")
    if serp_status not in NO_SERP_MESSAGES:
        serp_status = "lookup_failed"
    message = NO_SERP_MESSAGES[serp_status]

    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()(
            {
                "type": "run",
                "step": "run.failed",
                "error_code": "no_serp_data",
                "serp_status": serp_status,
                "message": message,
            }
        )
    except Exception as exc:  # noqa: BLE001 - reporting never breaks the flow
        logger.warning("no_serp_data stream emit failed: %s", exc)

    # A keyword nobody searches for is the user's to fix; a failed lookup is
    # an outage or a configuration fault an operator should see.
    if serp_status == "lookup_failed":
        try:
            from src.services.monitoring_service import MonitoringService

            await MonitoringService.persist_error_log(
                api_severity="medium",
                message="Content generation stopped: the SERP lookup failed",
                source="flow rext.no_serp_data",
                path="/flow/rext/no_serp_data",
                metadata={
                    "error_code": "no_serp_data",
                    "serp_status": serp_status,
                    "workspace_id": str(
                        (state.get("serp_payload") or {}).get("workspace_id") or ""
                    ),
                },
            )
        except Exception:  # noqa: BLE001 - reporting never breaks the flow
            pass

    return {"content": {"error": message, "error_code": "no_serp_data"}}
