from src.flow.states.rext import REXT
import logging
import sentry_sdk
from sentry_sdk import capture_message, push_scope

logger = logging.getLogger(__name__)

MAX_OUTLINE_ITERATIONS = 3  # Maximum times the outline can loop before forcing content generation

def outline_router(state: REXT) -> str:
    """
    Routes the workflow based on outline approval status.
    
    Returns:
        - "generate_content" if outline approved or max iterations reached
        - "generate_outline" to continue editing
    """
    content_state = state.get("content", {})
    outline_state = content_state.get("outline", {})
    outline_status = outline_state.get("status", "")

    # Track loop iterations in state
    iteration_count = outline_state.get("iteration_count", 0)

    if outline_status == "approved":
        with push_scope() as scope:
            scope.set_tag("module", "outline_router")
            scope.set_tag("status", "approved")
            scope.set_context("routing_info", {"iteration_count": iteration_count})
            capture_message("Outline approved, proceeding to content generation", level="info")
        return "generate_content"

    if iteration_count >= MAX_OUTLINE_ITERATIONS:
        with push_scope() as scope:
            scope.set_tag("module", "outline_router")
            scope.set_tag("status", "max_iterations_reached")
            scope.set_context("iteration_info", {
                "max_iterations": MAX_OUTLINE_ITERATIONS,
                "current_iteration": iteration_count
            })
            capture_message(
                f"Max outline iterations ({MAX_OUTLINE_ITERATIONS}) reached, forcing content generation",
                level="warning"
            )
        return "generate_content"

    with push_scope() as scope:
        scope.set_tag("module", "outline_router")
        scope.set_tag("status", "outline_not_approved")
        scope.set_context("iteration_info", {
            "current_iteration": iteration_count + 1,
            "max_iterations": MAX_OUTLINE_ITERATIONS
        })
        capture_message(
            f"Outline not approved (iteration {iteration_count + 1}/{MAX_OUTLINE_ITERATIONS}), re-running outline generation",
            level="info"
        )
    return "generate_outline"

