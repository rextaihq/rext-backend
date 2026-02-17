
import asyncio
from typing import Optional
from uuid import UUID
from src.services.sse_service import (
    event_stream_manager,
    OperationEvent,
)
from src.api.lib.logger import auto_logger
from src.utils.payload_sanitizer import sanitize_notification_payload

logger = auto_logger()

# Maximum number of publish attempts before giving up
_MAX_PUBLISH_RETRIES = 2
# Delay in seconds between retry attempts
_RETRY_DELAY_SECONDS = 0.5


class NotificationService:
    """A stateless service for sending user notifications via SSE."""

    @staticmethod
    async def _send_notification(
        user_id: UUID,
        message: str,
        step: str,
        status: str,
        payload: Optional[dict] = None,
    ):
        """Helper method to construct and publish a notification event.

        Wraps the SSE publish call with error handling and a single retry.
        If all attempts fail, the error is logged but not re-raised so that
        callers (especially BackgroundTasks) are not disrupted.
        """
        operation_id = f"user-notifications-{user_id}"
        event = OperationEvent(
            operation_id=operation_id,
            scope="notification",
            step=step,
            status=status,
            message=message,
            payload=sanitize_notification_payload(payload) or {},
        )

        # Ensure this user owns their notification channel (Security from TASK-274)
        await event_stream_manager.set_operation_owner(operation_id, user_id)

        last_exception: Optional[Exception] = None

        for attempt in range(1, _MAX_PUBLISH_RETRIES + 1):
            try:
                logger.info(
                    f"Publishing notification event for user {user_id}: "
                    f"{message} (attempt {attempt}/{_MAX_PUBLISH_RETRIES})"
                )
                await event_stream_manager.publish(event, publisher_user_id=user_id)
                # Success -- exit the retry loop
                return
            except asyncio.CancelledError:
                # CancelledError must always be re-raised per Python async
                # best practices to avoid breaking structured concurrency.
                logger.warning(
                    f"Notification publish cancelled for user {user_id}: "
                    f"{message}"
                )
                raise
            except Exception as exc:
                last_exception = exc
                logger.error(
                    f"Failed to publish notification event for user "
                    f"{user_id} (attempt {attempt}/{_MAX_PUBLISH_RETRIES}): "
                    f"{type(exc).__name__}: {exc}",
                    exc_info=True,
                )
                if attempt < _MAX_PUBLISH_RETRIES:
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)

        # All retries exhausted -- log a final error but do NOT re-raise.
        # Notifications are important but should not crash the calling flow.
        logger.error(
            f"All {_MAX_PUBLISH_RETRIES} attempts to publish notification "
            f"for user {user_id} have failed. Last error: "
            f"{type(last_exception).__name__}: {last_exception}. "
            f"Notification lost: step={step}, status={status}, "
            f"message={message}"
        )

    @staticmethod
    async def send_notification_to_user(
        user_id: UUID, message: str, payload: Optional[dict] = None
    ) -> None:
        """Sends a general real-time notification to a specific user."""
        await NotificationService._send_notification(
            user_id, message, "new_message", "new", payload
        )

    @staticmethod
    async def send_success_notification(
        user_id: UUID, message: str, payload: Optional[dict] = None
    ) -> None:
        """Sends a success notification."""
        logger.info(f"Preparing to send success notification to user {user_id}")
        await NotificationService._send_notification(
            user_id, message, "success", "completed", payload
        )

    @staticmethod
    async def send_error_notification(
        user_id: UUID, message: str, payload: Optional[dict] = None
    ) -> None:
        """Sends an error notification."""
        await NotificationService._send_notification(
            user_id, message, "error", "failed", payload
        )

    @staticmethod
    async def send_warning_notification(
        user_id: UUID, message: str, payload: Optional[dict] = None
    ) -> None:
        """Sends a warning notification."""
        await NotificationService._send_notification(
            user_id, message, "warning", "warning", payload
        )

    @staticmethod
    async def send_info_notification(
        user_id: UUID, message: str, payload: Optional[dict] = None
    ) -> None:
        """Sends an info notification."""
        await NotificationService._send_notification(
            user_id, message, "info", "info", payload
        )

    @staticmethod
    async def send_system_notification(
        user_id: UUID, message: str, payload: Optional[dict] = None
    ) -> None:
        """Sends a system-level notification."""
        await NotificationService._send_notification(
            user_id, message, "system", "system", payload
        )


# Create a singleton instance to be imported and used by other services
notification_service = NotificationService()