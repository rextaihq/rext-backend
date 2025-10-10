from __future__ import annotations

from typing import Dict
from uuid import UUID

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from src.api.security.dependencies import get_current_user
from src.services.sse_service import event_stream_manager
from src.utils.logger import logger


router = APIRouter(
    prefix="/events",
    tags=["events"],
)


@router.get(
    "/{operation_id}",
    summary="Subscribe to operation events",
    response_model=None,
)
async def subscribe_to_operation_events(
    operation_id: str,
    current_user: Dict[str, str] = Depends(get_current_user),
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
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # TODO: Verify requesting user owns the operation being accessed.

    return EventSourceResponse(
        event_stream_manager.subscribe(operation_id, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
