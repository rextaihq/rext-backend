from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.server import app


class _ScalarResult:
    def __init__(self, invitations: list[Any]) -> None:
        self._invitations = invitations

    class _Scalars:
        def __init__(self, invitations: list[Any]) -> None:
            self._invitations = invitations

        def all(self) -> list[Any]:  # pragma: no cover - trivial
            return self._invitations

    def scalars(self) -> "_ScalarResult._Scalars":  # pragma: no cover - trivial
        return self._Scalars(self._invitations)


@pytest.mark.asyncio
async def test_list_workspace_invitations_restful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the RESTful invitations endpoint returns invitations."""
    workspace_id = uuid4()
    user_id = uuid4()

    invitation = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        email="invitee@example.com",
        role_id=uuid4(),
        status="pending",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_user_id=user_id,
    )

    class _InvitationDB:
        async def execute(self, *_args: Any, **_kwargs: Any) -> _ScalarResult:
            return _ScalarResult([invitation])

    async def override_get_db() -> AsyncGenerator[_InvitationDB, None]:
        yield _InvitationDB()

    def override_current_user() -> dict[str, str]:
        return {"identity": str(user_id)}

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_invitations.verify_current_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_invitations.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_id), SimpleNamespace())),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_invitations._load_role_map",
        AsyncMock(return_value={invitation.role_id: SimpleNamespace(display_name="Editor")}),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_invitations._load_user_map",
        AsyncMock(return_value={user_id: SimpleNamespace(display_name="Inviter")}),
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                f"/api/v1/workspaces/{workspace_id}/invitations"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    invitations = body["data"]["invitations"]
    assert len(invitations) == 1
    assert invitations[0]["email"] == "invitee@example.com"
