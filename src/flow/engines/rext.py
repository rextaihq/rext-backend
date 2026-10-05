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
    from src.flow.engines.seo.seo_engine import create_seo_engine
    from src.flow.engines.serp.serp_engine import create_serp_engine

    flow = StateGraph(REXT)

    flow.add_node("serp_engine", create_serp_engine())
    flow.add_node("seo_engine", create_seo_engine())
    flow.add_node("content_engine", create_content_engine())
    flow.add_node("insufficient_credits", _insufficient_credits)

    flow.add_conditional_edges(
        START,
        library_router,
        {
            "serp_engine": "serp_engine",
            "content_engine": "content_engine",
            "insufficient_credits": "insufficient_credits",
        },
    )

    flow.add_edge("serp_engine", "seo_engine")
    # A changed keyword or country must re-run the SERP engine too, otherwise the
    # recommendations/competitors of the previous analysis would be reused.
    flow.add_conditional_edges(
        "seo_engine",
        keyword_router,
        {"SERP_ENGINE": "serp_engine", "END": "content_engine"},
    )
    flow.add_edge("content_engine", END)
    flow.add_edge("insufficient_credits", END)

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
