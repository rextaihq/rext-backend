from __future__ import annotations

from typing import Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sse_starlette.sse import EventSourceResponse

from src.api.security.dependencies import get_current_user, get_current_user_sse
from src.services.sse_service import event_stream_manager
from src.utils.logger import logger


router = APIRouter(
    prefix="/events",
    tags=["events"],
)

# Matches plain UUIDs and prefixed UUIDs (e.g., "user-notifications-<uuid>")
# Allows lowercase alphanumeric characters and hyphens, 1-100 chars
OPERATION_ID_PATTERN = r"^[a-z0-9](?:[a-z0-9\-]{0,98}[a-z0-9])?$"


@router.get(
    "/{operation_id}",
    summary="Subscribe to operation events",
    response_model=None,
)
async def subscribe_to_operation_events(
    operation_id: str = Path(
        ...,
        min_length=1,
        max_length=100,
        pattern=OPERATION_ID_PATTERN,
        description="Operation identifier (UUID or prefixed-UUID format)",
    ),
    current_user: Dict[str, str] = Depends(get_current_user_sse),
) -> EventSourceResponse:
    """
    Establish a Server-Sent Events stream for a specific background operation.

    Args:
        operation_id: Unique identifier for the long-running operation
        current_user: Authenticated user dictionary provided by dependency

    Returns:
        EventSourceResponse streaming SSE messages in real time.
    """

    user_id = UUID(str(current_user.get("identity")))
    logger.info(
        "SSE subscription requested",
        extra={"operation_id": operation_id, "user_id": str(user_id)},
    )

    # Verify requesting user owns the operation being accessed
    is_owner = await event_stream_manager.verify_operation_ownership(operation_id, user_id)
    if not is_owner:
        logger.warning(
            "Unauthorized SSE subscription attempt",
            extra={"operation_id": operation_id, "user_id": str(user_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this operation"
        )

    # Check if operation is already completed
    # If it is, return a special SSE stream with completion event
    if await event_stream_manager.is_operation_completed(operation_id):
        logger.info(
            "SSE subscription to completed operation",
            extra={"operation_id": operation_id, "user_id": str(user_id)},
        )
        return EventSourceResponse(
            event_stream_manager.subscribe_completed(operation_id, user_id),
            media_type="text/event-stream",
            ping=15,
            send_timeout=5,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
                "X-Accel-Buffering": "no",
            },
        )

    return EventSourceResponse(
        event_stream_manager.subscribe(operation_id, user_id),
        media_type="text/event-stream",
        ping=15,
        send_timeout=5,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
            "X-Accel-Buffering": "no",
        },
    )
