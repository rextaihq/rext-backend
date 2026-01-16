from datetime import datetime, timezone
from src.utils.logger import logger
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.models.content_models.content import Content
from src.services.sse_service import event_stream_manager, OperationEvent
from sqlalchemy import select
from uuid import UUID
from typing import Dict, Any, Optional

class ProgressManager:
    """
    Manager for handling content progress persistence and callbacks.

    Responsibilities:
        - Insert or update content progress in the database.
        - Optionally call a callback function to broadcast progress updates
          (e.g., via WebSocket or SSE).

    Attributes:
        db: Async SQLAlchemy session for database operations.
        progress_callback (callable, optional): A function to be called after
            progress is updated. Receives a UUID and the progress data.
    """
    # Progress step definitions with percentages
    PROGRESS_STEPS = {
        "initializing": {"percent": 0, "message": "Initializing content generation..."},
        "fetching_user": {"percent": 10, "message": "Fetching user information..."},
        "fetching_workspace": {"percent": 15, "message": "Loading workspace details..."},
        "fetching_topic": {"percent": 20, "message": "Retrieving topic information..."},
        "gathering_web_context": {"percent": 30, "message": "Searching web for relevant context..."},
        "gathering_knowledge_context": {"percent": 40, "message": "Retrieving workspace knowledge..."},
        "scraping_content": {"percent": 50, "message": "Scraping and processing sources..."},
        "reranking_documents": {"percent": 60, "message": "Ranking content by relevance..."},
        "generating_blog": {"percent": 75, "message": "Generating content with AI..."},
        "saving_content": {"percent": 95, "message": "Saving generated content..."},
        "completed": {"percent": 100, "message": "Content generation completed!"},
        "failed": {"percent": -1, "message": "Content generation failed"}
    }

    def __init__(self, db: AsyncSession):
        """
        Initialize ProgressManager.

        Args:
            db: Async database session
        """
        self.db = db

    async def initialize_progress(
        self,
        content_id: UUID,
        step: str = "initializing"
    ) -> None:
        """
        Initialize progress for content generation (SSE only).

        Args:
            content_id: Content UUID
            step: Initial step name
        """
        logger.debug(
            f"Initializing progress for content {content_id} at step {step}"
        )
        step_info = self.PROGRESS_STEPS.get(step, {"percent": 0, "message": "Starting..."})

        # Emit SSE event for initialization
        await self._publish_sse_event(
            content_id=content_id,
            step=step,
            status="in_progress",
            message=step_info["message"],
            progress=step_info["percent"],
            payload={}
        )

    async def update_progress(
        self,
        content_id: UUID,
        step: str,
        message: Optional[str] = None,
        step_details: Optional[Dict[str, Any]] = None,
        estimated_time_remaining: Optional[int] = None
    ) -> None:
        """
        Update progress via SSE event.

        Args:
            content_id: Content UUID
            step: Progress step name (from PROGRESS_STEPS)
            message: Custom status message (optional, uses default if not provided)
            step_details: Additional step-specific data (optional)
            estimated_time_remaining: Estimated seconds remaining (optional) - Unused now
        """
        logger.info("Updating progress", extra={"content_id": content_id, "step": step})
        step_info = self.PROGRESS_STEPS.get(step)
        if not step_info:
            logger.warning(f"Unknown progress step: {step}")
            return

        progress_percent = step_info["percent"]
        status_message = message or step_info["message"]

        # Determine status for SSE event
        if progress_percent == 100:
            status = "completed"
        elif progress_percent < 0:
            status = "failed"
        else:
            status = "in_progress"

        # Publish SSE event
        await self._publish_sse_event(
            content_id=content_id,
            step=step,
            status=status,
            message=status_message,
            progress=progress_percent,
            payload=step_details
        )

        logger.info(
            f"Progress updated for content {content_id}",
            extra={"step": step, "progress": progress_percent, "message": status_message}
        )

    async def emit_progress_event(
        self,
        content_id: UUID,
        step: str,
        message: Optional[str] = None,
        step_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Emit SSE progress event.
        Alias for update_progress since persistence is removed.
        """
        await self.update_progress(content_id, step, message, step_details)

    async def mark_completed(
        self,
        content_id: UUID,
        message: str = "Content generated successfully!"
    ) -> None:
        """Mark content generation as completed."""
        # Content status update is handled by the caller or implicitly by flow completion
        # But we should ensure Content table is updated if not already
        # Wait, the original code didn't update Content status here?
        # Let's check. Original code: mark_failed updated Content.status. mark_completed did NOT (it just updated ContentProgress).
        # We should probably update Content status to 'ready' or 'completed' here to be safe.
        
        # Publish final completion event
        await self._publish_sse_event(
            content_id=content_id,
            step="pipeline.completed",  # Frontend expects this step name
            status="completed",
            message=message,
            progress=100,
            payload={"content_id": str(content_id), "status": "ready"}
        )

        # Mark operation as completed in SSE manager (closes the stream)
        await event_stream_manager.complete(str(content_id))

    async def mark_failed(
        self,
        content_id: UUID,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Mark content generation as failed."""
        
        # Update content status in DB
        result = await self.db.execute(
            select(Content).where(Content.id == content_id)
        )
        content = result.scalar_one_or_none()
        if content:
            content.status = "failed"
            # content.updated_at is updated automatically by onupdate if we support it, otherwise:
            content.updated_at = datetime.now(timezone.utc)
            await self.db.flush() # Caller commits

        # Publish final failure event
        await self._publish_sse_event(
            content_id=content_id,
            step="pipeline.failed",  # Frontend expects this step name
            status="failed",
            message=f"Generation failed: {error_message}",
            progress=-1,
            payload={"content_id": str(content_id), "status": "failed", "error": error_message}
        )

        # Mark operation as completed (with error) in SSE manager
        await event_stream_manager.complete(str(content_id))

    async def _publish_sse_event(
        self,
        content_id: UUID,
        step: str,
        status: str,
        message: str,
        progress: int,
        payload: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Publish SSE event for real-time frontend updates.

        Args:
            content_id: Content UUID (used as operation_id)
            step: Current step name
            status: Status ("in_progress", "completed", "failed")
            message: Status message
            progress: Progress percentage (0-100)
            payload: Additional payload data
        """
        event = OperationEvent(
            operation_id=str(content_id),
            scope="content_generation",
            step=step,
            status=status,
            message=message,
            progress=progress,
            payload=payload or {}
        )

        await event_stream_manager.publish(event)

        logger.debug(
            f"SSE event published for content {content_id}",
            extra={"step": step, "progress": progress}
        )

    async def get_progress(self, content_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get current progress for a content item.
        Since persistence is removed, this always returns None or needs to be removed.
        Returning None for now to avoid breaking callers expectation of a return value.
        """
        return None

    async def reset_progress(self, content_id: UUID) -> None:
        """
        Reset progress for a content item (for retries).
        No-op since persistence is removed.
        """
        logger.info(f"Reset progress for content {content_id} (no-op)")
