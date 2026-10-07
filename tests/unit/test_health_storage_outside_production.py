"""Media storage is critical for /health and /health/ready in production only."""

import json
from contextlib import asynccontextmanager

import pytest

import src.api.database.async_database as async_database
import src.api.server as server


class _Session:
    def __init__(self, fail: bool):
        self.fail = fail

    async def execute(self, *_args, **_kwargs):
        if self.fail:
            raise RuntimeError("database down")


@pytest.fixture
def stack(monkeypatch):
    """Database up and storage down by default; the test picks the environment."""
    state = {"db_fails": False, "storage_ok": False}

    @asynccontextmanager
    async def fake_db_context():
        yield _Session(state["db_fails"])

    monkeypatch.setattr(async_database, "get_async_db_context", fake_db_context)
    monkeypatch.setattr(server.storage_service, "check_connection", lambda: state["storage_ok"])

    def environment(name):
        monkeypatch.setattr(server.settings, "ENVIRONMENT", name)

    state["environment"] = environment
    return state


async def _call(endpoint):
    response = await endpoint(None)
    return response.status_code, json.loads(response.body)


@pytest.mark.asyncio
async def test_health_without_storage_is_degraded_but_up_outside_production(stack):
    stack["environment"]("development")
    code, body = await _call(server.health_check)
    assert code == 200
    assert body["status"] == "degraded"
    assert body["checks"]["storage"].startswith("unhealthy")


@pytest.mark.asyncio
async def test_health_without_storage_is_down_in_production(stack):
    stack["environment"]("production")
    code, body = await _call(server.health_check)
    assert code == 503
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_without_the_database_is_down_everywhere(stack):
    stack["environment"]("development")
    stack["db_fails"] = True
    stack["storage_ok"] = True
    code, body = await _call(server.health_check)
    assert code == 503
    assert body["checks"]["database"].startswith("unhealthy")


@pytest.mark.asyncio
async def test_ready_without_storage_outside_production(stack):
    stack["environment"]("staging")
    code, body = await _call(server.readiness_check)
    assert code == 200
    assert body["status"] == "ready"
    assert body["checks"]["storage"].startswith("not_ready")


@pytest.mark.asyncio
async def test_not_ready_without_storage_in_production(stack):
    stack["environment"]("production")
    code, body = await _call(server.readiness_check)
    assert code == 503
    assert body["status"] == "not_ready"
