from src.flow.states.rext import REXT

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
        logger.info("Outline approved, proceeding to content generation")
        return "generate_content"

    if iteration_count >= MAX_OUTLINE_ITERATIONS:
        logger.warning(
            "Max outline iterations (%d) reached, forcing content generation",
            MAX_OUTLINE_ITERATIONS
        )
        return "generate_content"

    logger.info(
        "Outline not approved (iteration %d/%d), re-running outline generation",
        iteration_count + 1,
        MAX_OUTLINE_ITERATIONS
    )
    return "generate_outline"

