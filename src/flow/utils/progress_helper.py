"""
Progress Helper for Workflow Nodes

Provides synchronous wrapper for updating progress from workflow nodes.
Since nodes are sync functions but progress updates need async DB operations,
this helper uses asyncio.run() to execute async operations.
"""
from typing import Optional, Dict, Any
from uuid import UUID

from src.api.database.async_database import get_async_db

from src.utils.logger import logger


def update_node_progress(
    content_id: str,
    step: str,
    message: Optional[str] = None,
    step_details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Synchronous wrapper to update progress from workflow nodes.

    NOTE: Progress updates from LangGraph nodes are disabled to avoid event loop conflicts.
    Progress is now tracked by the main workflow controller via LangGraph event streaming.

    Args:
        content_id: Content UUID as string
        step: Progress step name (from ContentProgressService.PROGRESS_STEPS)
        message: Custom status message (optional)
        step_details: Additional step data (optional)

    Example:
        def my_workflow_node(state: ContentState):
            content_id = state["request_payload"]["content_id"]
            update_node_progress(content_id, "fetching_user")  # This is now a no-op
            # ... rest of node logic
    """
    # Disabled: Progress updates from nodes cause event loop conflicts
    # because Lang Graph runs nodes in thread pools but database connections
    # are tied to the main event loop.
    #
    # Instead, progress is tracked by observing LangGraph node execution events
    # in the main workflow controller (langgraph_content_service.py)
    logger.debug(
        f"Node progress update (disabled): {step}",
        extra={"content_id": content_id, "step": step}
    )
    return


from src.flow.service.process_manager import ProgressManager


async def _async_update_progress(
    content_id: str,
    step: str,
    message: Optional[str],
    step_details: Optional[Dict[str, Any]]
) -> None:
    """
    Internal async function to update progress.

    Creates its own database session and handles the update.
    """
    async for db in get_async_db():
        try:
            progress_service = ProgressManager(db)

            await progress_service.update_progress(
                content_id=UUID(content_id),
                step=step,
                message=message,
                step_details=step_details
            )

            await db.commit()

        except Exception as e:
            logger.error(f"Error in async progress update: {str(e)}")
            await db.rollback()
        finally:
            await db.close()
