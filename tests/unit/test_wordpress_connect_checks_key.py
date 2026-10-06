"""Connecting a WordPress site tests its key first, as the Test button does: the
plugin's authenticated /verify has to accept it. Before, only the plugin's
namespace index was read (it answers anyone), and a site without the plugin let
any key through."""

from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

ROUTES = "src.api.routes.integrations.wordpress"


class _FakePublisher:
    status = "connected"

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def check_connection(self):
        return {"status": self.status, "message": f"plugin says {self.status}"}


class _DB:
    def __init__(self) -> None:
        self.added = []

    def add(self, row) -> None:
        row.id, row.created_at = uuid4(), None
        self.added.append(row)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@pytest.fixture
def connect(monkeypatch, allow_permissions):
    from src.api.database.async_database import get_async_db
    from src.api.security.dependencies import get_current_user
    from src.api.server import app

    db, reported = _DB(), []
    workspace_id = uuid4()
    monkeypatch.setattr(
        f"{ROUTES}.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_id), None)),
    )
    # example.com would be resolved through DNS; the address check has its own tests.
    monkeypatch.setattr(f"{ROUTES}.ensure_public_site_urls", AsyncMock())
    monkeypatch.setattr(f"{ROUTES}.ensure_no_duplicate_integration", AsyncMock())
    monkeypatch.setattr(f"{ROUTES}.WordPressPublisher", _FakePublisher)
    monkeypatch.setattr(
        "src.services.monitoring_service.MonitoringService.report_third_party_failure",
        AsyncMock(side_effect=lambda **kwargs: reported.append(kwargs)),
    )

    async def override_db() -> AsyncGenerator[_DB, None]:
        yield db

    app.dependency_overrides[get_async_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(uuid4())}

    async def _connect(status: str):
        _FakePublisher.status = status
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/integrations/wordpress/",
                params={"workspace_id": str(workspace_id)},
                json={
                    "integration_type": "wordpress",
                    "is_active": True,
                    "site_url": "https://example.com",
                    "api_endpoint": "https://example.com/wp-json/rext-ai/v1/",
                    "api_key": "a-key",
                },
            )
        return response, db.added, reported

    yield _connect
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["invalid_credentials", "plugin_missing", "plugin_disabled"])
async def test_a_key_the_plugin_does_not_accept_is_not_connected(connect, status):
    response, added, reported = await connect(status)

    assert response.status_code == 422
    assert response.json()["message"] == f"plugin says {status}"
    assert added == []
    assert reported == []


@pytest.mark.asyncio
async def test_a_site_that_does_not_answer_is_refused_and_reported(connect):
    response, added, reported = await connect("unreachable")

    assert response.status_code == 422
    assert added == []
    assert [r["metadata"]["status"] for r in reported] == ["unreachable"]


@pytest.mark.asyncio
async def test_a_key_the_plugin_accepts_is_connected(connect):
    response, added, _ = await connect("connected")

    assert response.status_code == 200
    (site,) = added
    assert site.site_url == "https://example.com"
    assert site.api_key == "a-key"
