"""
Route-level authorization tests: which permission each endpoint enforces.

The caller's permission list is stubbed underneath the real require_permissions /
PermissionChecker code, and workspace resolution is stubbed to stop the handler
right after the guard (404). So 403 means "denied by the permission guard" and
404 means "passed the guard". Dashboard isolation runs against the test DB.
"""

from typing import AsyncGenerator, Callable
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.middleware.permissions import PermissionChecker
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.security.dependencies import get_current_user
from src.api.server import app
from src.services.role_service import RoleService


@pytest.fixture
def grant(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Authenticated non-super-admin caller over a mock DB; call grant(*perms) to set permissions."""
    user_id = uuid4()

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_async_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user_id), "roles": []}
    monkeypatch.setattr("src.utils.rbac_utils.is_user_super_admin", AsyncMock(return_value=False))

    def _grant(*permissions: str) -> None:
        monkeypatch.setattr(
            "src.utils.rbac_utils.get_user_permissions",
            AsyncMock(return_value=list(permissions)),
        )

    yield _grant
    app.dependency_overrides.clear()


def _stop_after_guard() -> AsyncMock:
    return AsyncMock(
        side_effect=ResourceNotFoundException(resource_type="workspace", resource_id="stub")
    )


async def _status(method: str, url: str, json: dict[str, str] | None = None) -> int:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.request(method, url, json=json)
    return response.status_code


# ---------------------------------------------------------------------------
# Publish authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["publish", "retry"])
async def test_publish_denied_with_content_create_but_without_publish(grant, monkeypatch, action):
    monkeypatch.setattr(
        "src.api.routes.content.modules.publish_content.resolve_and_verify_workspace",
        _stop_after_guard(),
    )
    grant("content.read", "content.create", "content.update")

    status = await _status("POST", f"/api/v1/content/{uuid4()}/{action}?workspace_id={uuid4()}")

    assert status == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["publish", "retry"])
async def test_publish_allowed_with_content_publish(grant, monkeypatch, action):
    monkeypatch.setattr(
        "src.api.routes.content.modules.publish_content.resolve_and_verify_workspace",
        _stop_after_guard(),
    )
    grant("content.read", "content.publish")

    status = await _status("POST", f"/api/v1/content/{uuid4()}/{action}?workspace_id={uuid4()}")

    assert status == 404


# ---------------------------------------------------------------------------
# Member / invitation authorization
# ---------------------------------------------------------------------------


def _stub_member_routes(monkeypatch: pytest.MonkeyPatch, module: str) -> None:
    monkeypatch.setattr(f"src.api.routes.workspaces.{module}.verify_current_user", AsyncMock())
    monkeypatch.setattr(
        f"src.api.routes.workspaces.{module}.resolve_and_verify_workspace", _stop_after_guard()
    )


@pytest.mark.asyncio
async def test_member_role_change_denied_with_member_update_only(grant, monkeypatch):
    _stub_member_routes(monkeypatch, "workspace_members")
    grant("member.read", "member.update")

    status = await _status(
        "PATCH",
        f"/api/v1/workspaces/{uuid4()}/members/{uuid4()}/role",
        json={"role_id": str(uuid4())},
    )

    assert status == 403


@pytest.mark.asyncio
async def test_member_role_change_allowed_with_member_update_role(grant, monkeypatch):
    _stub_member_routes(monkeypatch, "workspace_members")
    grant("member.read", "member.update", "member.update_role")

    status = await _status(
        "PATCH",
        f"/api/v1/workspaces/{uuid4()}/members/{uuid4()}/role",
        json={"role_id": str(uuid4())},
    )

    assert status == 404


@pytest.mark.asyncio
async def test_invitation_resend_requires_member_invite(grant, monkeypatch):
    _stub_member_routes(monkeypatch, "workspace_invitations")
    url = f"/api/v1/workspaces/{uuid4()}/invitations/{uuid4()}/resend"

    grant("member.read")
    assert await _status("POST", url) == 403

    grant("member.read", "member.invite")
    assert await _status("POST", url) == 404


@pytest.mark.asyncio
async def test_invitation_revoke_requires_member_invite(grant, monkeypatch):
    _stub_member_routes(monkeypatch, "workspace_invitations")
    url = f"/api/v1/workspaces/{uuid4()}/invitations/{uuid4()}"

    grant("member.read")
    assert await _status("DELETE", url) == 403

    grant("member.read", "member.invite")
    assert await _status("DELETE", url) == 404


# ---------------------------------------------------------------------------
# Integration authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_site_management_requires_integration_delete(grant, monkeypatch):
    monkeypatch.setattr(
        "src.api.routes.content.modules.sites.resolve_and_verify_workspace", _stop_after_guard()
    )
    url = f"/api/v1/content/sites/{uuid4()}?workspace_id={uuid4()}"

    grant("content.read", "content.create", "content.update", "content.delete")
    assert await _status("DELETE", url) == 403

    grant("integration.read", "integration.delete")
    assert await _status("DELETE", url) == 404


@pytest.mark.asyncio
async def test_shopify_integration_delete_requires_integration_delete(grant, monkeypatch):
    monkeypatch.setattr(PermissionChecker, "_is_super_admin", AsyncMock(return_value=False))
    monkeypatch.setattr(
        PermissionChecker, "_validate_workspace_membership", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        PermissionChecker,
        "_get_user_permissions",
        AsyncMock(return_value=["user.read", "content.delete", "integration.read"]),
    )

    status = await _status("DELETE", f"/api/v1/integrations/shopify/?workspace_id={uuid4()}")

    assert status == 403


# ---------------------------------------------------------------------------
# System roles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_role_route_ignores_client_is_system_role(grant, monkeypatch):
    captured: dict[str, object] = {}

    class _CapturingRoleService:
        def __init__(self, db: AsyncMock) -> None:
            self.db = db

        async def create_role(self, **kwargs: object) -> None:
            captured.update(kwargs)
            raise ResourceNotFoundException(resource_type="role", resource_id="stub")

    monkeypatch.setattr("src.api.routes.roles.modules.role_crud.RoleService", _CapturingRoleService)
    grant("role.read", "role.create")

    status = await _status(
        "POST",
        "/api/v1/roles/",
        json={
            "name": "sneaky_role",
            "display_name": "Sneaky Role",
            "hierarchy_level": 1,
            "is_system_role": True,
        },
    )

    assert status == 404
    assert "is_system_role" not in captured
    assert captured["acting_user_id"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "suffix", "service_method"),
    [
        ("POST", "permissions", "add_permissions_to_role"),
        ("PUT", "permissions", "update_role_permissions"),
        ("DELETE", f"permissions/{uuid4()}", "remove_permission_from_role"),
    ],
)
async def test_role_permission_routes_pass_acting_user_for_hierarchy_check(
    grant, monkeypatch, method, suffix, service_method
):
    captured: dict[str, object] = {}

    async def _capture(self, *args: object, **kwargs: object) -> None:
        captured.update(kwargs)
        raise ResourceNotFoundException(resource_type="role", resource_id="stub")

    monkeypatch.setattr(RoleService, service_method, _capture)
    grant("role.read", "role.manage_permissions")

    # PUT reads the role's current permission ids for the audit diff before
    # calling the service; give db.execute(...).all() something iterable.
    async def override_db_with_rows() -> AsyncGenerator[AsyncMock, None]:
        db = AsyncMock()
        db.execute = AsyncMock(return_value=Mock(all=Mock(return_value=[])))
        yield db

    app.dependency_overrides[get_async_db] = override_db_with_rows
    body = {"permission_ids": [str(uuid4())]} if method != "DELETE" else None

    status = await _status(method, f"/api/v1/roles/{uuid4()}/{suffix}", json=body)

    assert status == 404
    assert captured["acting_user_id"] is not None


# ---------------------------------------------------------------------------
# System Monitoring (security.*) and Audit Logs (audit.*)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitoring_view_requires_security_read_not_audit(grant):
    url = "/api/v1/admin/monitoring/error-logs"

    grant("audit.read", "audit.export")
    assert await _status("GET", url) == 403

    grant("security.read")
    assert await _status("GET", url) != 403


@pytest.mark.asyncio
async def test_monitoring_resolve_requires_security_manage(grant):
    url = f"/api/v1/admin/monitoring/error-logs/{uuid4()}/resolve"

    grant("security.read")
    assert await _status("PATCH", url) == 403

    grant("security.read", "security.manage")
    assert await _status("PATCH", url) != 403


@pytest.mark.asyncio
async def test_audit_logs_require_audit_read_not_security(grant):
    url = "/api/v1/audit-logs/"

    grant()
    assert await _status("GET", url) == 403

    grant("security.read", "security.manage")
    assert await _status("GET", url) == 403

    grant("audit.read")
    assert await _status("GET", url) != 403


@pytest.mark.asyncio
async def test_audit_export_requires_audit_export(grant):
    url = "/api/v1/audit-logs/export/download?format=csv"

    grant("audit.read")
    assert await _status("GET", url) == 403

    grant("audit.read", "audit.export")
    assert await _status("GET", url) != 403


# ---------------------------------------------------------------------------
# Workspace isolation (DB-backed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["dashboard", "recent-activities"])
async def test_non_member_cannot_read_other_workspace(client, setup_factories, path):
    outsider = await setup_factories["user"].create()
    owner = await setup_factories["user"].create()
    workspace_b = await setup_factories["workspace"].create(user_id=owner.id)
    content = await setup_factories["content"].create(
        workspace_id=workspace_b.id, created_by_user_id=owner.id
    )
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(outsider.id)}

    response = await client.get(f"/api/v1/{path}/{workspace_b.id}")

    assert response.status_code == 404
    assert content.title not in response.text


@pytest.mark.asyncio
async def test_member_can_read_own_workspace_recent_activities(client, db_session, setup_factories):
    member = await setup_factories["user"].create()
    workspace = await setup_factories["workspace"].create(user_id=member.id)
    db_session.add(
        WorkspaceMembers(id=uuid4(), workspace_id=workspace.id, user_id=member.id, status="active")
    )
    await db_session.flush()
    content = await setup_factories["content"].create(
        workspace_id=workspace.id, created_by_user_id=member.id
    )
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(member.id)}

    response = await client.get(f"/api/v1/recent-activities/{workspace.id}")

    assert response.status_code == 200
    assert content.title in response.text


# ---------------------------------------------------------------------------
# User management authorization (SEC-RBAC-01/02/03: user.manage, not the
# self-service user.read / user.update every account holds)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,url",
    [
        ("GET", "/api/v1/user/users"),
        ("GET", f"/api/v1/user/detail/{uuid4()}"),
        ("PUT", f"/api/v1/user/update/{uuid4()}"),
        ("POST", f"/api/v1/user/{uuid4()}/suspend"),
        ("POST", f"/api/v1/user/{uuid4()}/ban"),
    ],
)
async def test_admin_user_routes_denied_with_only_self_service_permissions(grant, method, url):
    # A default 'user' account holds exactly these; none may reach admin actions.
    grant("user.read", "user.update")
    body = {"reason": "x"} if method == "POST" else {"full_name": "x"}
    assert await _status(method, url, json=body) == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,url",
    [
        ("GET", "/api/v1/user/users"),
        ("PUT", f"/api/v1/user/update/{uuid4()}"),
        ("POST", f"/api/v1/user/{uuid4()}/suspend"),
    ],
)
async def test_admin_user_routes_pass_guard_with_user_manage(grant, method, url):
    grant("user.manage")
    body = {"reason": "x"} if method == "POST" else {"full_name": "x"}
    # Past the permission guard the handler runs against a mock DB, so anything
    # other than 403 means the guard admitted the caller.
    assert await _status(method, url, json=body) != 403


@pytest.fixture
def support_role_user(grant, monkeypatch):
    """grant() setup, but the caller holds the global support role."""
    grant()
    app.dependency_overrides[get_current_user] = lambda: {
        "identity": str(uuid4()),
        "roles": ["support"],
    }
    monkeypatch.setattr(
        "src.utils.rbac_utils.get_user_permissions",
        AsyncMock(return_value=[]),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/user/users",
        f"/api/v1/user/detail/{uuid4()}",
    ],
)
async def test_user_read_routes_admit_support_role(support_role_user, url):
    # Support gets READ-ONLY visibility via its global role. user.read cannot
    # gate this: every account holds it for self-service.
    assert await _status("GET", url) != 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,url",
    [
        ("PUT", f"/api/v1/user/update/{uuid4()}"),
        ("POST", f"/api/v1/user/{uuid4()}/suspend"),
        ("POST", f"/api/v1/user/{uuid4()}/ban"),
    ],
)
async def test_user_write_routes_denied_for_support_role(support_role_user, method, url):
    # Read-only: support must not reach any cross-user write action.
    body = {"reason": "x"} if method == "POST" else {"full_name": "x"}
    assert await _status(method, url, json=body) == 403
