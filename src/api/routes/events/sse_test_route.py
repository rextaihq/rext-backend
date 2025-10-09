from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from src.utils.logger import logger

router = APIRouter(
    tags=["events"],
    responses={404: {"description": "Not found"}},
)


async def _heartbeat_stream(request: Request) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Yield periodic heartbeat events for SSE smoke testing.

    Generates an initial connection event followed by heartbeats until the
    client disconnects.
    """
    connection_event_id = str(uuid4())
    yield {
        "event": "connection.established",
        "id": connection_event_id,
        "retry": 5000,
        "data": json.dumps(
            {
            "message": "SSE connection established",
            "event_id": connection_event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        ),
    }

    heartbeat_count = 0

    while True:
        if await request.is_disconnected():
            logger.info("SSE test client disconnected")
            break

        heartbeat_count += 1
        event_id = str(uuid4())
        payload = {
            "message": "Heartbeat",
            "sequence": heartbeat_count,
            "event_id": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        yield {
            "event": "connection.heartbeat",
            "id": event_id,
            "data": json.dumps(payload),
        }

        await asyncio.sleep(1)


@router.get(
    "/test",
    summary="SSE connectivity smoke test",
    description="Streams heartbeat events to verify Server-Sent Events are configured correctly.",
)
async def stream_test_events(request: Request) -> EventSourceResponse:
    """
    Provide a test SSE stream to validate CORS, connectivity, and clients.

    Returns:
        EventSourceResponse: Continuous SSE heartbeat stream.
    """

    logger.info("SSE test stream requested")
    return EventSourceResponse(
        _heartbeat_stream(request),
        media_type="text/event-stream",
    )
