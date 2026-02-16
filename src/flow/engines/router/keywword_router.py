import logging
from langgraph.graph import StateGraph, START, END
from src.flow.states.rext import REXT

def keyword_router(state: REXT)->str:
    """Route keyword recommendation loop based on state changes.

    Returns ``"SEO_ENGINE"`` if keywords were changed by user selection
    (triggering another SEO analysis iteration), or ``"END"`` to exit
    the loop.

    Args:
        state: REXT state containing ``seo_result.keyword_recommendations.is_changed``.

    Returns:
        str: Either ``"SEO_ENGINE"`` or ``"END"``.
    """
    if state["seo_result"]["keyword_recommendations"]["is_changed"]:
        return "SEO_ENGINE"
    return "END"