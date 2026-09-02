from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.server import app


@pytest.fixture
def workspace_context(monkeypatch: pytest.MonkeyPatch) -> dict[str, UUID]:
    """Prepare shared workspace context and core dependency overrides."""

    workspace_id = uuid4()
    user_id = uuid4()

    class _DummyDB:
        pass

    async def override_get_db() -> AsyncGenerator[_DummyDB, None]:
        yield _DummyDB()

    def override_current_user() -> dict[str, str]:
        return {"identity": str(user_id)}

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_knowledge.verify_current_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_knowledge.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_id), SimpleNamespace())),
    )

    return {"workspace_id": workspace_id, "user_id": user_id}


@pytest.mark.asyncio
async def test_get_workspace_knowledge_returns_combined_payload(
    monkeypatch: pytest.MonkeyPatch,
    workspace_context: dict[str, UUID],
) -> None:
    """Ensure aggregate endpoint returns data from all knowledge domains."""

    workspace_id = workspace_context["workspace_id"]

    class _KnowledgeServiceStub:
        def __init__(self, _db: Any) -> None:
            self.calls: dict[str, UUID] = {}

        async def list_web_knowledge(self, received_workspace_id: UUID) -> list[dict[str, Any]]:
            self.calls["web"] = received_workspace_id
            return [{"id": "web-1", "title": "Example", "url": "https://example.com"}]

        async def list_file_knowledge(self, received_workspace_id: UUID) -> list[dict[str, Any]]:
            self.calls["file"] = received_workspace_id
            return [{"id": "file-1", "name": "Spec.pdf"}]

        async def list_text_knowledge(self, received_workspace_id: UUID) -> list[dict[str, Any]]:
            self.calls["text"] = received_workspace_id
            return [{"id": "text-1", "title": "Overview"}]

    stub = _KnowledgeServiceStub(_db=None)
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_knowledge.KnowledgeService",
        lambda db: stub,
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/knowledge",
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["summary"]["total_count"] == 3
    assert data["web_knowledge"][0]["id"] == "web-1"
    assert data["file_knowledge"][0]["id"] == "file-1"
    assert data["text_knowledge"][0]["id"] == "text-1"
    assert stub.calls == {
        "web": workspace_id,
        "file": workspace_id,
        "text": workspace_id,
    }


@pytest.mark.asyncio
async def test_create_web_knowledge_invokes_service_and_updates_title(
    monkeypatch: pytest.MonkeyPatch,
    workspace_context: dict[str, UUID],
) -> None:
    """Verify POST /knowledge/web creates entry and applies optional title."""

    workspace_id = workspace_context["workspace_id"]

    class _KnowledgeServiceStub:
        def __init__(self, _db: Any) -> None:
            self.created_url: str | None = None
            self.updated_title: str | None = None
            self.created_id = uuid4()

        async def add_web_knowledge(self, received_workspace_id: UUID, url: str) -> dict[str, Any]:
            assert received_workspace_id == workspace_id
            self.created_url = url
            return {"id": str(self.created_id), "url": url, "title": None}

        async def update_web_knowledge_title(
            self,
            received_workspace_id: UUID,
            knowledge_id: UUID,
            title: str,
        ) -> dict[str, Any]:
            assert received_workspace_id == workspace_id
            assert knowledge_id == self.created_id
            self.updated_title = title
            return {"id": str(self.created_id), "url": "https://rext.ai", "title": title}

    stub = _KnowledgeServiceStub(_db=None)
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_knowledge.KnowledgeService",
        lambda db: stub,
    )
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_all_permissions",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "src.utils.workspace_utils.async_get_workspace_id_from_identifier",
        AsyncMock(return_value=workspace_id),
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/knowledge/web",
                json={"url": "https://rext.ai", "title": "Homepage"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()["data"]["web_knowledge"]
    assert payload["title"] == "Homepage"
    assert stub.created_url == "https://rext.ai"
    assert stub.updated_title == "Homepage"


@pytest.mark.asyncio
async def test_create_file_knowledge_returns_serialized_payload(
    monkeypatch: pytest.MonkeyPatch,
    workspace_context: dict[str, UUID],
) -> None:
    """Uploading a file should delegate to service and return serialized data."""

    workspace_id = workspace_context["workspace_id"]

    class _FileKnowledge(SimpleNamespace):
        def to_dict(self) -> dict[str, Any]:  # pragma: no cover - simple conversion
            return dict(self.__dict__)

    class _KnowledgeServiceStub:
        def __init__(self, _db: Any) -> None:
            self.received_filename: str | None = None

        async def add_file_knowledge(
            self,
            workspace_id_arg: UUID,
            file: Any,
            allowed_types: list[str],
            max_size_mb: int,
        ) -> _FileKnowledge:
            assert workspace_id_arg == workspace_id
            assert max_size_mb == 10
            self.received_filename = file.filename
            return _FileKnowledge(id="file-xyz", name=file.filename)

    stub = _KnowledgeServiceStub(_db=None)
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_knowledge.KnowledgeService",
        lambda db: stub,
    )
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_all_permissions",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "src.utils.workspace_utils.async_get_workspace_id_from_identifier",
        AsyncMock(return_value=workspace_id),
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/knowledge/files",
                files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["file_knowledge"]["id"] == "file-xyz"
    assert stub.received_filename == "notes.txt"


@pytest.mark.asyncio
async def test_create_text_knowledge_returns_payload(
    monkeypatch: pytest.MonkeyPatch,
    workspace_context: dict[str, UUID],
) -> None:
    """POST /knowledge/text should persist textual knowledge via service."""

    workspace_id = workspace_context["workspace_id"]

    class _TextKnowledge(SimpleNamespace):
        pass

    class _KnowledgeServiceStub:
        def __init__(self, _db: Any) -> None:
            self.payloads: list[tuple[UUID, str, str]] = []

        async def add_text_knowledge(
            self,
            workspace_id_arg: UUID,
            title: str,
            content: str,
        ) -> _TextKnowledge:
            assert workspace_id_arg == workspace_id
            self.payloads.append((workspace_id_arg, title, content))
            return _TextKnowledge(
                id=uuid4(), workspace_id=workspace_id, title=title, content=content
            )

    stub = _KnowledgeServiceStub(_db=None)
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_knowledge.KnowledgeService",
        lambda db: stub,
    )
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_all_permissions",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "src.utils.workspace_utils.async_get_workspace_id_from_identifier",
        AsyncMock(return_value=workspace_id),
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_id}/knowledge/text",
                json={"title": "Summary", "content": "Key ideas from kickoff"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    text_payload = body["data"]["text_knowledge"]
    assert text_payload["title"] == "Summary"
    assert stub.payloads[0][1] == "Summary"
