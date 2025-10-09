from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.server import app


class _ResultWithAll:
    """Simple helper mimicking SQLAlchemy result.all()."""

    def __init__(self, rows: list[tuple[Any, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Any, Any]]:  # pragma: no cover - trivial
        return self._rows


class _ResultWithScalar:
    """Simple helper mimicking SQLAlchemy scalar_one_or_none()."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:  # pragma: no cover - trivial
        return self._value


@pytest.mark.asyncio
async def test_list_workspace_members_restful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the RESTful members endpoint returns serialized members."""
    workspace_id = uuid4()
    user_id = uuid4()

    member = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        workspace_id=workspace_id,
        status="active",
        is_default=False,
        joined_at=None,
        last_activity_at=None,
    )
    user = SimpleNamespace(
        id=member.user_id,
        email="member@example.com",
        display_name="Member One",
        email_verified=True,
    )

    class _MembersDB:
        async def execute(self, *_args: Any, **_kwargs: Any) -> _ResultWithAll:
            return _ResultWithAll([(member, user)])

    async def override_get_db() -> AsyncGenerator[_MembersDB, None]:
        yield _MembersDB()

    def override_current_user() -> dict[str, str]:
        return {"identity": str(user_id)}

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.verify_current_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_id), SimpleNamespace())),
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(f"/api/v1/workspaces/{workspace_id}/members")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    members = payload["data"]["members"]
    assert len(members) == 1
    assert members[0]["user"]["email"] == "member@example.com"


@pytest.mark.asyncio
async def test_add_workspace_member_restful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure POST /members creates a member and returns serialized payload."""
    workspace_uuid = uuid4()
    user_id = uuid4()
    invited_user = SimpleNamespace(
        id=uuid4(),
        email="invitee@example.com",
        display_name="Invited User",
        deleted_at=None,
    )
    new_member = SimpleNamespace(
        id=uuid4(),
        user_id=invited_user.id,
        workspace_id=workspace_uuid,
        status="active",
        is_default=False,
        joined_at=None,
        last_activity_at=None,
    )

    class _MembersDB:
        def __init__(self) -> None:
            self._executed = False

        async def execute(self, *_args: Any, **_kwargs: Any) -> _ResultWithScalar:
            if self._executed:
                raise AssertionError("execute called more times than expected")
            self._executed = True
            return _ResultWithScalar(invited_user)

    async def override_get_db() -> AsyncGenerator[_MembersDB, None]:
        yield _MembersDB()

    def override_current_user() -> dict[str, str]:
        return {"identity": str(user_id)}

    class _MemberServiceStub:
        def __init__(self, _db: Any) -> None:
            pass

        async def add_member(
            self,
            workspace_id: UUID,
            user_id: UUID,
        ) -> SimpleNamespace:
            assert workspace_id == workspace_uuid
            assert user_id == invited_user.id
            return new_member

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.verify_current_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_uuid), SimpleNamespace())),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.MemberService",
        _MemberServiceStub,
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_uuid}/members",
                json={"email": invited_user.email},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    member_payload = body["data"]["member"]
    assert member_payload["user"]["email"] == invited_user.email
