"""Ending a run whose stage charge was refused, before the next stage uses its work."""

from langgraph.graph import END

from src.flow.states.rext import REXT

OUT_OF_CREDITS = "insufficient_credits"


def out_of_credits(state: REXT) -> bool:
    """Whether a stage left the run out of credits (its charge refused, or its pre-flight)."""
    return (state.get("content") or {}).get("error_code") == OUT_OF_CREDITS


def serp_unpaid(state: REXT) -> bool:
    """Whether the keyword analysis's SERP charge was refused, so its paid calls were skipped."""
    seo_result = state.get("seo_result") or {}
    return (seo_result.get("serp_backlinks") or {}).get("volume_status") == OUT_OF_CREDITS


def unless_out_of_credits(next_node: str):
    """A router that goes on to `next_node`, or ends the run when it ran out of credits."""

    def route(state: REXT) -> str:
        return END if out_of_credits(state) else next_node

    route.__name__ = f"to_{next_node}_unless_out_of_credits"
    return route
