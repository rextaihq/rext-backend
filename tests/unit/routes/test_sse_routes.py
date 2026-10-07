from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest

from src.api.routes.events import sse_routes
from src.api.security.dependencies import get_current_user_sse
from src.api.server import app
from src.services import sse_service


@pytest.mark.asyncio
async def test_sse_route_requires_authentication(client) -> None:
    response = await client.get("/api/v1/events/op-unauthorized")
    assert response.status_code in {401, 403, 422}


def _frames(text: str) -> list[list[str]]:
    """Each SSE frame's lines, as a client splits them (comments, such as pings, left out)."""
    frames = []
    for raw in text.replace("\r\n", "\n").split("\n\n"):
        lines = [line for line in raw.split("\n") if line and not line.startswith(":")]
        if lines:
            frames.append(lines)
    return frames


@pytest.fixture
def stream_user(monkeypatch):
    """A signed-in SSE user and a fresh event manager behind the route."""
    user_identity = uuid4()
    manager = sse_service.EventStreamManager(cleanup_interval_seconds=0)
    monkeypatch.setattr(sse_routes, "event_stream_manager", manager)
    app.dependency_overrides[get_current_user_sse] = lambda: {"identity": str(user_identity)}
    try:
        yield user_identity, manager
    finally:
        app.dependency_overrides.pop(get_current_user_sse, None)


def _event(operation_id: str, step: str, status: str) -> sse_service.OperationEvent:
    return sse_service.OperationEvent(
        operation_id=operation_id, scope="workspace", step=step, status=status, message=step
    )


@pytest.mark.asyncio
async def test_sse_route_streams_one_frame_per_event(client, stream_user) -> None:
    _, manager = stream_user
    operation_id = "op-success"
    started = _event(operation_id, "scrape.started", "started")

    async def publish_once_subscribed() -> None:
        while not (
            operation_id in await manager.active_operation_ids()
            and manager._operations[operation_id].subscribers
        ):
            await asyncio.sleep(0.01)
        await manager.publish(started)
        await manager.complete(operation_id)

    publisher = asyncio.create_task(publish_once_subscribed())
    response = await asyncio.wait_for(client.get(f"/api/v1/events/{operation_id}"), timeout=5)
    await publisher

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/event-stream")
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("X-Accel-Buffering") == "no"

    connected, published = _frames(response.text)
    assert [line.split(": ", 1)[0] for line in connected] == ["id", "event", "data"]
    assert connected[1] == "event: connection.connected"
    assert published == [
        f"id: {started.id}",
        "event: workspace.scrape.started",
        f"data: {started.model_dump_json()}",
    ]
    # Never a frame wrapped inside data: (the bug this replaces).
    assert "data: id:" not in response.text and "data: event:" not in response.text


@pytest.mark.asyncio
async def test_sse_route_for_a_completed_operation(client, stream_user) -> None:
    _, manager = stream_user
    operation_id = "op-finished"
    await manager.publish(_event(operation_id, "pipeline.completed", "completed"))
    await manager.complete(operation_id)

    response = await asyncio.wait_for(client.get(f"/api/v1/events/{operation_id}"), timeout=5)

    frames = _frames(response.text)
    assert [frame[1] for frame in frames] == [
        "event: connection.connected",
        "event: workspace.pipeline.completed",
    ]
    assert json.loads(frames[1][2].removeprefix("data: "))["status"] == "completed"
