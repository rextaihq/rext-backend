from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.server import app


class _DummyDB:
    """Minimal async session stub for route testing."""

    async def commit(self) -> None:  # pragma: no cover - trivial
        return None

    async def rollback(self) -> None:  # pragma: no cover - trivial
        return None


@pytest.mark.asyncio
async def test_update_brand_voice_restful_returns_serialized_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure RESTful brand voice endpoint serializes service payload correctly."""
    workspace_identifier = uuid4()
    user_identifier = uuid4()

    async def override_get_db() -> AsyncGenerator[_DummyDB, None]:
        yield _DummyDB()

    def override_current_user() -> dict[str, str]:
        return {"identity": str(user_identifier)}

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    brand_voice_stub = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_identifier,
        about="Updated about",
        customer_profile="Ideal customers",
        selling_position="Unique value",
        target_audience=["Audience A"],
        brand_voice=["Friendly"],
        competitors=["Competitor"],
        content_strategy=["Strategy"],
        created_at=None,
        updated_at=None,
    )

    # Patch security + workspace helpers used in route decorators/logic
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.verify_current_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_identifier), MagicMock())),
    )
    monkeypatch.setattr(
        "src.utils.workspace_utils.async_get_workspace_id_from_identifier",
        AsyncMock(return_value=workspace_identifier),
    )
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_all_permissions",
        AsyncMock(return_value=True),
    )

    # Patch service to capture invocation
    service_mock = AsyncMock()
    service_mock.upsert_brand_voice = AsyncMock(return_value=brand_voice_stub)

    class ServiceFactory:
        def __init__(self, db: Any) -> None:
            self.db = db

        async def upsert_brand_voice(self, workspace_id: UUID, user_id: UUID, brand_data: Any):
            return await service_mock.upsert_brand_voice(workspace_id, user_id, brand_data)

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.BrandVoiceService",
        ServiceFactory,
    )

    payload = {
        "about": "Updated about",
        "customer_profile": "Ideal customers",
        "selling_position": "Unique value",
        "target_audience": ["Audience A"],
        "brand_voice": ["Friendly"],
        "competitors": ["Competitor"],
        "content_strategy": ["Strategy"],
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                f"/api/v1/workspaces/{workspace_identifier}/brand-voice",
                json=payload,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    response_payload = body["data"]["brand_voice"]

    assert response_payload["about"] == "Updated about"
    assert response_payload["customer_profile"] == "Ideal customers"
    assert response_payload["selling_position"] == "Unique value"
    assert response_payload["target_audience"] == ["Audience A"]
    assert response_payload["brand_voice"] == ["Friendly"]
    assert response_payload["competitors"] == ["Competitor"]
    assert response_payload["content_strategy"] == ["Strategy"]
    assert response_payload["workspace_id"] == str(workspace_identifier)
    assert response_payload["id"] == str(brand_voice_stub.id)

    service_mock.upsert_brand_voice.assert_awaited_once()
    called_workspace_id, called_user_id, brand_data = service_mock.upsert_brand_voice.await_args[0]
    assert called_workspace_id == workspace_identifier
    assert called_user_id == user_identifier
    # Ensure original request payload surfaced through BrandSchema
    assert brand_data.about == "Updated about"
    assert brand_data.strategy == ["Strategy"]


@pytest.mark.asyncio
async def test_refresh_brand_voice_returns_operation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure refresh endpoint schedules pipeline and returns operation ID."""
    workspace_identifier = uuid4()
    user_identifier = uuid4()
    operation_id = "test-operation"

    async def override_get_db() -> AsyncGenerator[_DummyDB, None]:
        yield _DummyDB()

    def override_current_user() -> dict[str, str]:
        return {"identity": str(user_identifier)}

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    # Patch decorators dependencies
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.verify_current_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_identifier), MagicMock())),
    )
    monkeypatch.setattr(
        "src.utils.workspace_utils.async_get_workspace_id_from_identifier",
        AsyncMock(return_value=workspace_identifier),
    )
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_all_permissions",
        AsyncMock(return_value=True),
    )

    service_mock = AsyncMock()
    service_mock.refresh_brand_voice_for_user = AsyncMock(return_value=operation_id)

    class ServiceFactory:
        def __init__(self, db: Any) -> None:
            self.db = db

        async def refresh_brand_voice_for_user(self, workspace_id: UUID, user_id: UUID):
            return await service_mock.refresh_brand_voice_for_user(workspace_id, user_id)

        async def upsert_brand_voice(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - unused
            raise NotImplementedError

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.WorkspaceService",
        ServiceFactory,
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_identifier}/brand-voice/refresh",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["operation_id"] == operation_id

    service_mock.refresh_brand_voice_for_user.assert_awaited_once_with(
        workspace_identifier,
        user_identifier,
    )
@pytest.mark.asyncio
async def test_get_brand_voice_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure GET brand voice endpoint returns serialized payload."""
    workspace_identifier = uuid4()
    user_identifier = uuid4()

    async def override_get_db() -> AsyncGenerator[_DummyDB, None]:
        yield _DummyDB()

    def override_current_user() -> dict[str, str]:
        return {"identity": str(user_identifier)}

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    brand_voice_stub = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_identifier,
        about="Test about",
        customer_profile="Test customers",
        selling_position="Test position",
        target_audience=[],
        brand_voice=[],
        competitors=[],
        content_strategy=[],
        created_at=None,
        updated_at=None,
    )

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.verify_current_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_identifier), MagicMock())),
    )
    monkeypatch.setattr(
        "src.utils.workspace_utils.async_get_workspace_id_from_identifier",
        AsyncMock(return_value=workspace_identifier),
    )
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_all_permissions",
        AsyncMock(return_value=True),
    )

    service_mock = AsyncMock()
    service_mock.get_brand_voice = AsyncMock(return_value=brand_voice_stub)

    class ServiceFactory:
        def __init__(self, db: Any) -> None:
            self.db = db

        async def get_brand_voice(self, workspace_id: UUID, user_id: UUID):
            return await service_mock.get_brand_voice(workspace_id, user_id)

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.BrandVoiceService",
        ServiceFactory,
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                f"/api/v1/workspaces/{workspace_identifier}/brand-voice",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["brand_voice"]["about"] == "Test about"


@pytest.mark.asyncio
async def test_delete_brand_voice_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure DELETE brand voice endpoint returns success."""
    workspace_identifier = uuid4()
    user_identifier = uuid4()

    async def override_get_db() -> AsyncGenerator[_DummyDB, None]:
        yield _DummyDB()

    def override_current_user() -> dict[str, str]:
        return {"identity": str(user_identifier)}

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.verify_current_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_identifier), MagicMock())),
    )
    monkeypatch.setattr(
        "src.utils.workspace_utils.async_get_workspace_id_from_identifier",
        AsyncMock(return_value=workspace_identifier),
    )
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_all_permissions",
        AsyncMock(return_value=True),
    )

    service_mock = AsyncMock()
    service_mock.delete_brand_voice = AsyncMock(return_value=True)

    class ServiceFactory:
        def __init__(self, db: Any) -> None:
            self.db = db

        async def delete_brand_voice(self, workspace_id: UUID, user_id: UUID):
            return await service_mock.delete_brand_voice(workspace_id, user_id)

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_brand_voice.BrandVoiceService",
        ServiceFactory,
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.delete(
                f"/api/v1/workspaces/{workspace_identifier}/brand-voice",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["deleted"] is True
