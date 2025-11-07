from datetime import datetime, timezone
from src.api.models.content_models.content_progress import ContentProgress
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
        Initialize ContentProgressService.

        Args:
            db: Async database session
        """
        self.db = db

    async def initialize_progress(
        self,
        content_id: UUID,
        step: str = "initializing"
    ) -> ContentProgress:
        """
        Create initial progress record for content generation.

        Args:
            content_id: Content UUID
            step: Initial step name

        Returns:
            Created ContentProgress record
        """
        logger.debug(
            f"Initializing progress for content {content_id} at step {step}"
        )
        step_info = self.PROGRESS_STEPS.get(step, {"percent": 0, "message": "Starting..."})

        progress = ContentProgress(
            content_id=content_id,
            current_step=step,
            progress_percent=step_info["percent"],
            status_message=step_info["message"],
            step_details={},
            estimated_time_remaining=600,  # 10 minutes default
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        self.db.add(progress)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(progress)

        logger.info(
            f"Progress initialized for content {content_id}",
            extra={"step": step, "progress": step_info["percent"]}
        )

        # Emit SSE event for initialization
        await self._publish_sse_event(
            content_id=content_id,
            step=step,
            status="in_progress",
            message=step_info["message"],
            progress=step_info["percent"],
            payload={}
        )

        return progress

    async def update_progress(
        self,
        content_id: UUID,
        step: str,
        message: Optional[str] = None,
        step_details: Optional[Dict[str, Any]] = None,
        estimated_time_remaining: Optional[int] = None
    ) -> None:
        """
        Update progress in database and publish SSE event.

        Args:
            content_id: Content UUID
            step: Progress step name (from PROGRESS_STEPS)
            message: Custom status message (optional, uses default if not provided)
            step_details: Additional step-specific data (optional)
            estimated_time_remaining: Estimated seconds remaining (optional)
        """
        logger.info("Updating progress", extra={"content_id": content_id, "step": step})
        step_info = self.PROGRESS_STEPS.get(step)
        if not step_info:
            logger.warning(f"Unknown progress step: {step}")
            return

        progress_percent = step_info["percent"]
        status_message = message or step_info["message"]

        # Update or create progress record
        result = await self.db.execute(
            select(ContentProgress).where(ContentProgress.content_id == content_id)
        )
        progress = result.scalar_one_or_none()

        if progress:
            progress.current_step = step
            progress.progress_percent = progress_percent
            progress.status_message = status_message
            if step_details:
                progress.step_details = step_details
            if estimated_time_remaining is not None:
                progress.estimated_time_remaining = estimated_time_remaining
            progress.updated_at = datetime.now(timezone.utc)
        else:
            # Create if doesn't exist
            progress = await self.initialize_progress(content_id, step)
            progress.status_message = status_message
            if step_details:
                progress.step_details = step_details

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(progress)
        

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
        Emit SSE progress event WITHOUT updating database.

        Use this for intermediate steps to show real-time progress to frontend
        without the overhead of database writes. The database should only be
        updated for stable states (initializing, completed, failed).

        Args:
            content_id: Content UUID
            step: Progress step name (from PROGRESS_STEPS)
            message: Custom status message (optional, uses default if not provided)
            step_details: Additional step-specific data (optional)
        """
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

        # Publish SSE event only (no DB update)
        await self._publish_sse_event(
            content_id=content_id,
            step=step,
            status=status,
            message=status_message,
            progress=progress_percent,
            payload=step_details
        )

        logger.debug(
            f"Progress event emitted for content {content_id}",
            extra={"step": step, "progress": progress_percent}
        )

    async def mark_completed(
        self,
        content_id: UUID,
        message: str = "Content generated successfully!"
    ) -> None:
        """Mark content generation as completed."""
        await self.update_progress(
            content_id=content_id,
            step="completed",
            message=message,
            estimated_time_remaining=0
        )

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
        await event_stream_manager.complete(str(content_id))  # Fixed: complete() not mark_completed()

    async def mark_failed(
        self,
        content_id: UUID,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Mark content generation as failed."""
        await self.update_progress(
            content_id=content_id,
            step="failed",
            message=f"Generation failed: {error_message}",
            step_details=error_details or {"error": error_message},
            estimated_time_remaining=0
        )

        # Update content status
        result = await self.db.execute(
            select(Content).where(Content.id == content_id)
        )
        content = result.scalar_one_or_none()
        if content:
            content.status = "failed"
            content.updated_at = datetime.now(timezone.utc)
            await self.db.flush()

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
        await event_stream_manager.complete(str(content_id))  # Fixed: complete() not mark_completed()

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

        await event_stream_manager.publish(event)  # Fixed: publish() not publish_event()

        logger.debug(
            f"SSE event published for content {content_id}",
            extra={"step": step, "progress": progress}
        )

    async def get_progress(self, content_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get current progress for a content item.

        Args:
            content_id: Content UUID

        Returns:
            Progress data dictionary or None
        """
        result = await self.db.execute(
            select(ContentProgress).where(ContentProgress.content_id == content_id)
        )
        progress = result.scalar_one_or_none()

        if not progress:
            return None

        return {
            "content_id": str(content_id),
            "current_step": progress.current_step,
            "progress_percent": progress.progress_percent,
            "status_message": progress.status_message,
            "step_details": progress.step_details,
            "estimated_time_remaining": progress.estimated_time_remaining,
            "updated_at": progress.updated_at.isoformat() if progress.updated_at else None
        }

    async def reset_progress(self, content_id: UUID) -> None:
        """
        Reset progress for a content item (for retries).

        Args:
            content_id: Content UUID
        """
        result = await self.db.execute(
            select(ContentProgress).where(ContentProgress.content_id == content_id)
        )
        progress = result.scalar_one_or_none()

        if progress:
            # Delete existing progress record
            await self.db.delete(progress)
            await self.db.flush()

        logger.info(f"Reset progress for content {content_id}")
