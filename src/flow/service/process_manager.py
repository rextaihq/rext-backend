from datetime import datetime, timezone
from src.api.models.content_models.content_progress import ContentProgress
from uuid import UUID
from sqlalchemy import select

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
    def __init__(self, db, progress_callback=None):
        """
        Initialize ProgressManager.

        Args:
            db: Async SQLAlchemy session.
            progress_callback (callable, optional): Optional callback to notify
                external systems about progress updates.
        """
        self.db = db
        self.progress_callback = progress_callback

    async def update_content_progress(self, content_id, data):
        """
        Insert or update a content progress record in the database.

        If a record already exists for the given `content_id`, updates the
        existing record; otherwise, creates a new record.

        Also triggers the optional `progress_callback` after updating.

        Args:
            content_id (str | UUID): Unique identifier for the content.
            data: ContentProgressResponse or similar object containing
                current_step, progress_percent, status_message, step_details.

        Returns:
            ContentProgress: The inserted or updated ContentProgress object.

        Raises:
            Exception: Re-raises any exception thrown by the callback function.
        """

        result = await self.db.execute(select(ContentProgress).where(ContentProgress.content_id == str(content_id)))
        progress = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if progress:
            progress.current_step = data.current_step
            progress.progress_percent = data.progress_percent
            progress.status_message = data.status_message
            progress.step_details = data.step_details
            progress.updated_at = now
        else:
            progress = ContentProgress(
                content_id=str(content_id),
                current_step=data.current_step,
                progress_percent=data.progress_percent,
                status_message=data.status_message,
                step_details=data.step_details,
                created_at=now,
                updated_at=now,
            )
            self.db.add(progress)

        await self.db.commit()

        if self.progress_callback:
            try:
                self.progress_callback(UUID(str(content_id)), data)
            except Exception:
                import logging
                logging.exception("progress_callback failed")

        return progress
