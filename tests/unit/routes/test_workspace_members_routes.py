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
    monkeypatch.setattr(
        "src.services.workspace_permission_service.WorkspacePermissionService.has_workspace_permission",
        AsyncMock(return_value=True),
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
async def test_add_workspace_member_creates_pending_invitation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /members must create a pending invitation, not an active membership.

    Regression test: this endpoint used to add the invited user directly as an
    active member (bypassing acceptance), which is the bug being fixed here.
    """
    from datetime import datetime, timezone

    workspace_uuid = uuid4()
    user_id = uuid4()
    viewer_role = SimpleNamespace(
        id=uuid4(),
        name="viewer",
        display_name="Viewer",
        is_workspace_role=True,
    )
    inviter = SimpleNamespace(
        id=user_id,
        email="owner@example.com",
        display_name="Workspace Owner",
        full_name="Workspace Owner",
    )
    invitation = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_uuid,
        email="invitee@example.com",
        role_id=viewer_role.id,
        status="pending",
        expires_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        invited_by_user_id=user_id,
        invitation_token="test-token",
    )

    class _MembersDB:
        """
        Two db.execute() calls happen for this request, in order:
        1. MemberLimitChecker's workspace lookup (dependency, runs first) —
           returning None makes it take the "workspace doesn't exist, let the
           endpoint handle it" early-return path, so it doesn't need a real
           Workspace/plan/count chain stubbed out.
        2. The handler's default 'viewer' role lookup.
        """

        def __init__(self) -> None:
            self._call_count = 0

        async def execute(self, *_args: Any, **_kwargs: Any) -> _ResultWithScalar:
            self._call_count += 1
            if self._call_count == 1:
                return _ResultWithScalar(None)
            return _ResultWithScalar(viewer_role)

    async def override_get_db() -> AsyncGenerator[_MembersDB, None]:
        yield _MembersDB()

    def override_current_user() -> dict[str, str]:
        return {"identity": str(user_id)}

    class _InvitationServiceStub:
        def __init__(self, _db: Any) -> None:
            pass

        async def create_invitation(self, **_kwargs: Any) -> SimpleNamespace:
            return invitation

    user_service_mock = AsyncMock()
    user_service_mock.get_user_by_id.return_value = inviter

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    # check_all_permissions/check_any_permission are imported locally inside
    # require_permissions' wrapper (not module attributes of route_decorators),
    # so they must be patched at their actual definition site.
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_all_permissions",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_any_permission",
        AsyncMock(return_value=True),
    )

    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.verify_current_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.resolve_and_verify_workspace",
        AsyncMock(
            return_value=(
                SimpleNamespace(id=workspace_uuid, name="Acme"),
                SimpleNamespace(),
            )
        ),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.InvitationService",
        lambda *args: _InvitationServiceStub(*args),
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.UserService",
        lambda *args: user_service_mock,
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.create_workspace_invitation_email",
        lambda **_kwargs: "<html></html>",
    )
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_members.send_workspace_invitation_email_task",
        AsyncMock(return_value=None),
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                f"/api/v1/workspaces/{workspace_uuid}/members",
                json={"email": invitation.email},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    invitation_payload = body["data"]["invitation"]
    assert invitation_payload["email"] == invitation.email
    assert invitation_payload["status"] == "pending"
