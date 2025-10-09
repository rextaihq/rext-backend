from __future__ import annotations

from typing import Dict
from uuid import UUID, uuid4

import pytest

from src.api.security.dependencies import get_current_user
from src.api.server import app
from src.services import sse_service


@pytest.mark.asyncio
async def test_sse_route_requires_authentication(client) -> None:
    response = await client.get("/api/v1/events/op-unauthorized")
    assert response.status_code in {401, 403, 422}


@pytest.mark.asyncio
async def test_sse_route_streams_events(client, monkeypatch) -> None:
    user_identity = uuid4()

    def override_current_user() -> Dict[str, str]:
        return {"identity": str(user_identity)}

    app.dependency_overrides[get_current_user] = override_current_user

    async def fake_subscribe(operation_id: str, subscriber_id: UUID):
        assert operation_id == "op-success"
        assert subscriber_id == user_identity
        yield "id: 1\nevent: connection.connected\ndata: {}\n\n"
        yield 'id: 2\nevent: workspace.test\ndata: {"message": "ok"}\n\n'

    monkeypatch.setattr(
        sse_service.event_stream_manager,
        "subscribe",
        fake_subscribe,
        raising=False,
    )

    try:
        response = await client.get("/api/v1/events/op-success")
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("text/event-stream")

        body = await response.aread()
        text = body.decode("utf-8")
        assert "event: connection.connected" in text
        assert "event: workspace.test" in text
        assert '"message": "ok"' in text
        assert response.headers.get("Cache-Control") == "no-cache"
        assert response.headers.get("X-Accel-Buffering") == "no"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
