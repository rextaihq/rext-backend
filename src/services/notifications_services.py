from typing import Optional
from uuid import UUID
from src.services.sse_service import (
    event_stream_manager,
    OperationEvent,
)
from src.api.lib.logger import auto_logger

logger = auto_logger()
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
        """Helper method to construct and publish a notification event."""
        operation_id = f"user-notifications-{user_id}"

        # Ensure this user owns their notification channel
        await event_stream_manager.set_operation_owner(operation_id, user_id)

        event = OperationEvent(
            operation_id=operation_id,
            scope="notification",
            step=step,
            status=status,
            message=message,
            payload=payload or {},
        )
        logger.info(f"Publishing notification event for user {user_id}: {message}")
        await event_stream_manager.publish(event, publisher_user_id=user_id)

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
