import logging

from src.flow.states.rext import REXT

logger = logging.getLogger(__name__)


def validation_router(state: REXT) -> str:
    """
    Routes the workflow based on validate_content's deterministic result.

    Returns:
        - "repair_content" if validation failed and repair attempts remain
        - "humanize_content" if validation passed, OR the only failures are
          humanization-owned (word count), OR repair attempts are
          exhausted (best-effort — the pipeline still completes and publishes,
          flagged via validation.gave_up for a future manual-QA view, rather
          than hard-stopping)
    """
    content_state = state.get("content", {})
    validation = (content_state.get("review") or {}).get("validation") or {}

    if validation.get("passed"):
        logger.info("validation_router: content passed validation, proceeding to humanize")
        return "humanize_content"

    # Failures owned by humanization (word count) never route to repair on their
    # own. Validations recorded before `repair_required` existed fall back to the
    # old pass/fail behaviour.
    if not validation.get("repair_required", True):
        logger.info(
            "validation_router: only humanization-owned checks failed (%s); skipping repair",
            [c.get("name") for c in validation.get("deferred_checks") or []],
        )
        return "humanize_content"

    if validation.get("gave_up"):
        logger.warning(
            "validation_router: repair attempts exhausted, proceeding best-effort to humanize"
        )
        return "humanize_content"

    logger.info("validation_router: validation failed, routing to repair_content")
    return "repair_content"
