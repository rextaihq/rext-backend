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
    from src.flow.engines.seo.library_item import (
        charge_library_start,
        library_charge_router,
        library_item_router,
        load_library_item,
    )
    from src.flow.engines.seo.seo_engine import create_seo_engine
    from src.flow.engines.serp.serp_engine import create_serp_engine

    flow = StateGraph(REXT)

    flow.add_node("serp_engine", create_serp_engine())
    flow.add_node("seo_engine", create_seo_engine())
    flow.add_node("content_engine", create_content_engine())
    flow.add_node("begin_run", _begin_run)
    flow.add_node("insufficient_credits", _insufficient_credits)
    flow.add_node("credit_check_failed", _credit_check_failed)
    flow.add_node("no_serp_data", _no_serp_data)
    flow.add_node("load_library_item", load_library_item)
    flow.add_node("charge_library_start", charge_library_start)

    # A new run on a thread starts clean: an earlier run's terminal error (out of
    # credits, say) must not end this one (rext-control#524).
    flow.add_edge(START, "begin_run")
    flow.add_conditional_edges(
        "begin_run",
        library_router,
        {
            "serp_engine": "serp_engine",
            "load_library_item": "load_library_item",
            "insufficient_credits": "insufficient_credits",
            "credit_check_failed": "credit_check_failed",
        },
    )

    # A Library start: the item's stored research, then a fresh SERP, or straight
    # to its charges when the analysis's search results are fresh (E24,
    # rext-control#496); an item that is not in the caller's Library ends the
    # run (E17, rext-control#368).
    flow.add_conditional_edges(
        "load_library_item",
        library_item_router,
        {"serp_engine": "serp_engine", "charge_library_start": "charge_library_start", "end": END},
    )

    # A search with no organic result ends the run here, before seo_engine
    # charges the serp_seo credit or calls the keyword overview (founder,
    # 2026-10-05: such a run is not charged). A Library start already has its
    # keyword research, so it goes from the SERP to its charges and on to the
    # content steps, without the keyword gate.
    flow.add_conditional_edges(
        "serp_engine",
        _after_serp,
        {
            "seo_engine": "seo_engine",
            "charge_library_start": "charge_library_start",
            "no_serp_data": "no_serp_data",
        },
    )
    flow.add_conditional_edges(
        "charge_library_start",
        library_charge_router,
        {"content_engine": "content_engine", "insufficient_credits": "insufficient_credits"},
    )
    # A changed keyword or country must re-run the SERP engine too, otherwise the
    # recommendations/competitors of the previous analysis would be reused.
    flow.add_conditional_edges(
        "seo_engine",
        keyword_router,
        {
            "SERP_ENGINE": "serp_engine",
            "END": "content_engine",
            "NO_SERP": "no_serp_data",
            "INSUFFICIENT": "insufficient_credits",
        },
    )
    flow.add_edge("content_engine", END)
    flow.add_edge("insufficient_credits", END)
    flow.add_edge("credit_check_failed", END)
    flow.add_edge("no_serp_data", END)

    return flow.compile()


def _blocked_at(state: REXT) -> str:
    """Where a run ran out of credits, for the operators' record."""
    from src.flow.engines.router.credits import OUT_OF_CREDITS, serp_unpaid

    is_library = bool((state.get("serp_payload") or {}).get("is_library"))
    if is_library and (state.get("content") or {}).get("error_code") == OUT_OF_CREDITS:
        return "library start charges"
    keyword_recs = (state.get("seo_result") or {}).get("keyword_recommendations") or {}
    if keyword_recs.get("titles_unpaid"):
        return "title_generation charge"
    if not is_library and serp_unpaid(state):
        return "serp_seo charge"
    return "library_router credit gate"


async def _insufficient_credits(state: REXT) -> dict:
    """Terminal node for runs that ran out of credits: the start's gate, or a refused stage charge."""
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
                "blocked_at": _blocked_at(state),
            },
        )
    except Exception:  # noqa: BLE001 - reporting never breaks the flow
        pass

    from src.flow.engines.router.credits import OUT_OF_CREDITS
    from src.flow.engines.seo.library_item import research_reused
    from src.services.generation_events import ANALYSIS, REFUSED, TITLES, announce_failed

    keyword_recs = (state.get("seo_result") or {}).get("keyword_recommendations") or {}
    # A Library start that reuses its analysis is charged for its titles only: a refusal there
    # is the titles' as much as a typed keyword's refused title charge is.
    at_titles = keyword_recs.get("titles_unpaid") or (
        bool((state.get("serp_payload") or {}).get("is_library")) and research_reused(state)
    )
    # A Library start makes two charges in one step, and that step has said which of them
    # was refused (charge_library_start): said again here, it would be counted twice.
    said = (
        bool((state.get("serp_payload") or {}).get("is_library"))
        and (state.get("content") or {}).get("error_code") == OUT_OF_CREDITS
    )
    if not said:
        announce_failed(state, stage=TITLES if at_titles else ANALYSIS, reason=REFUSED)
    return {
        "content": {
            "error": "Insufficient credits to generate content. Please upgrade your plan.",
            "error_code": "insufficient_credits",
        }
    }


# The marks a paid run leaves in its content so a resumed node doesn't charge twice
# (generate_content): the upfront stages, and the featured image on delivery.
_PAID_MARKS = ("credits_deducted", "image_credit_deducted")


async def _begin_run(state: REXT) -> dict:
    """A new run notes when it began (its analytics events count their seconds from it), and
    clears what an earlier run on this thread left in its content: its terminal error, its
    paid-charge marks, so this run's own charges are made, and its repairs, so this run's
    article has its own attempts and its own count."""
    from src.services.generation_events import run_start_mark

    content = state.get("content") or {}
    update: dict = run_start_mark()
    if (
        content.get("error") is not None
        or content.get("error_code") is not None
        or any(content.get(mark) for mark in _PAID_MARKS)
    ):
        update.update({"error": None, "error_code": None, **dict.fromkeys(_PAID_MARKS, False)})
    review = content.get("review") or {}
    if review.get("repair_attempts") or review.get("repair_history"):
        # The repair step counts its attempts in the thread's review and stops at the limit,
        # and skips a check an earlier attempt left as it was: an earlier article's attempts
        # say nothing about this one.
        update["review"] = {"repair_attempts": 0, "repair_history": []}
    return {"content": update}


CREDIT_CHECK_FAILED = (
    "We couldn't check your credits just now, so the run didn't start. Try again in a moment."
)


async def _credit_check_failed(state: REXT) -> dict:
    """Terminal node for a run whose credit check couldn't be read (library_router fails closed).

    Like no_serp_data, the message reaches the user twice: as a custom stream event (type "run",
    step "run.failed") for the generation view that is streaming, and as content.error in the
    thread state, which the dock's status poll reads (the dashboard's E27, rext-control#570).
    """
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()(
            {
                "type": "run",
                "step": "run.failed",
                "error_code": "credit_check_failed",
                "message": CREDIT_CHECK_FAILED,
            }
        )
    except Exception as exc:  # noqa: BLE001 - reporting never breaks the flow
        logger.warning("credit_check_failed stream emit failed: %s", type(exc).__name__)
    from src.services.generation_events import ANALYSIS, INTERNAL, announce_failed

    announce_failed(state, stage=ANALYSIS, reason=INTERNAL)
    return {"content": {"error": CREDIT_CHECK_FAILED, "error_code": "credit_check_failed"}}


# What the user reads when a run ends for want of search results, by the
# SERP fetch's serp_status.
def _after_serp(state: REXT) -> str:
    """After the SERP: none to work from, a Library start's charges and content steps, or the keyword step."""
    from src.flow.engines.serp.normalization import has_organic_results

    if not has_organic_results(state):
        return "no_serp_data"
    if (state.get("serp_payload") or {}).get("is_library"):
        return "charge_library_start"
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

    from src.services.generation_events import ANALYSIS, PROVIDER, REFUSED, announce_failed

    announce_failed(
        state, stage=ANALYSIS, reason=PROVIDER if serp_status == "lookup_failed" else REFUSED
    )
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
