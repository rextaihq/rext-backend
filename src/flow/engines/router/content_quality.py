import logging

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def validation_router(state: REXT) -> str:
    """
    Routes the workflow based on validate_content's deterministic result.

    Returns:
        - "repair_content" if validation failed and repair attempts remain
        - "humanize_content" if validation passed, OR repair attempts are
          exhausted (best-effort — the pipeline still completes and publishes,
          flagged via validation.gave_up for a future manual-QA view, rather
          than hard-stopping)
    """
    content_state = state.get("content", {})
    validation = (content_state.get("review") or {}).get("validation") or {}

    if validation.get("passed"):
        logger.info("validation_router: content passed validation, proceeding to humanize")
        return "humanize_content"

    if validation.get("gave_up"):
        logger.warning(
            "validation_router: repair attempts exhausted, proceeding best-effort to humanize"
        )
        return "humanize_content"

    logger.info("validation_router: validation failed, routing to repair_content")
    return "repair_content"
