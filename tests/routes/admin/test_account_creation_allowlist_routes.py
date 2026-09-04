"""
HTTP-level auth tests for the account-creation IP allowlist admin API.

Verifies the endpoints are protected exactly like the rest of the Admin API:
- an authenticated admin OR super_admin can list / add / update / delete
- an authenticated non-admin user gets 403
- an unauthenticated request (bad/absent token) is rejected (401 / 422)

The DB and the service layer are stubbed so these tests stay focused on the
route wiring (path registration, `is_admin` dependency, request/response
shapes) and need no database. Service-level behaviour (IP validation, cache,
fail-closed) is covered in
tests/unit/services/test_account_creation_allowlist_service.py and
tests/utils/test_ip_allowlist.py.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.database.async_database import get_async_db
from src.api.middleware.error_handler import setup_exception_handlers
from src.api.routes.admin import account_creation_allowlist_routes as allowlist_routes
from src.api.security.dependencies import get_current_user

ADMIN_ID = "11111111-1111-1111-1111-111111111111"
ENTRY_ID = "22222222-2222-2222-2222-222222222222"
BASE = "/api/v1/admin/account-creation-allowlist"


def _entry(**over):
    from src.api.models.admin_models.account_creation_ip_allowlist import (
        AccountCreationIpAllowlist,
    )

    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return AccountCreationIpAllowlist(
        id=UUID(over.get("id", ENTRY_ID)),
        ip_address=over.get("ip_address", "203.0.113.10"),
        label=over.get("label"),
        is_active=over.get("is_active", True),
        created_by=None,
        created_at=now,
        updated_at=now,
    )


class _StubService:
    """Stands in for AccountCreationAllowlistService inside the routes module."""

    calls: list = []

    def __init__(self, db):
        pass

    async def list_entries(self, include_inactive: bool = True):
        type(self).calls.append("list")
        return [_entry(), _entry(id="33333333-3333-3333-3333-333333333333", is_active=False)]

    async def add_entry(self, ip_address, label=None, admin_user_id=None, is_active=True):
        type(self).calls.append("add")
        return _entry(ip_address=ip_address, label=label, is_active=is_active)

    async def get_entry(self, entry_id):
        type(self).calls.append("get")
        return _entry(id=str(entry_id))

    async def update_entry(self, entry_id, **kwargs):
        type(self).calls.append(f"update:{sorted(kwargs)}")
        return _entry(id=str(entry_id), **kwargs)

    async def delete_entry(self, entry_id):
        type(self).calls.append("delete")


@pytest.fixture
def app_client():
    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(allowlist_routes.router, prefix="/api/v1/admin")

    async def _fake_db():
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.flush = AsyncMock()
        yield db

    app.dependency_overrides[get_async_db] = _fake_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield app, client
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(app_client):
    """Client whose requests carry an authenticated identity (role decided per test)."""
    app, client = app_client
    app.dependency_overrides[get_current_user] = lambda: {
        "identity": ADMIN_ID,
        "email": "admin@example.com",
    }
    return client


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------

def test_unauthenticated_invalid_token_is_401(app_client):
    _, client = app_client
    resp = client.get(BASE, headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_unauthenticated_missing_header_is_rejected(app_client):
    _, client = app_client
    resp = client.get(BASE)
    assert resp.status_code in (401, 422)
    assert resp.status_code != 200


@pytest.mark.parametrize("method,path", [
    ("POST", BASE),
    ("PATCH", f"{BASE}/{ENTRY_ID}"),
    ("DELETE", f"{BASE}/{ENTRY_ID}"),
])
def test_all_mutations_require_auth(app_client, method, path):
    _, client = app_client
    resp = client.request(method, path, headers={"Authorization": "Bearer bad"}, json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Authenticated but not an admin -> 403
# ---------------------------------------------------------------------------

def test_non_admin_user_is_forbidden(authed_client):
    with patch(
        "src.utils.rbac_utils.is_user_admin", new_callable=AsyncMock, return_value=False
    ):
        assert authed_client.get(BASE).status_code == 403
        assert authed_client.post(
            BASE, json={"ip_address": "203.0.113.10"}
        ).status_code == 403
        assert authed_client.patch(
            f"{BASE}/{ENTRY_ID}", json={"is_active": False}
        ).status_code == 403
        assert authed_client.delete(f"{BASE}/{ENTRY_ID}").status_code == 403


# ---------------------------------------------------------------------------
# Authenticated admin / super_admin -> full CRUD
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", ["admin", "super_admin"])
def test_admin_and_super_admin_can_crud(authed_client, role):
    _StubService.calls = []
    with patch(
        "src.utils.rbac_utils.is_user_admin", new_callable=AsyncMock, return_value=True
    ), patch.object(allowlist_routes, "AccountCreationAllowlistService", _StubService):

        # LIST
        r = authed_client.get(BASE)
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["total_count"] == 2
        assert body["entries"][0]["ip_address"] == "203.0.113.10"

        # ADD
        r = authed_client.post(BASE, json={"ip_address": "198.51.100.7", "label": "HQ"})
        assert r.status_code == 201
        assert r.json()["data"]["ip_address"] == "198.51.100.7"
        assert r.json()["data"]["label"] == "HQ"

        # UPDATE (activate/deactivate + relabel)
        r = authed_client.patch(f"{BASE}/{ENTRY_ID}", json={"is_active": False})
        assert r.status_code == 200
        assert r.json()["data"]["is_active"] is False

        r = authed_client.patch(f"{BASE}/{ENTRY_ID}", json={"label": "renamed"})
        assert r.status_code == 200
        assert r.json()["data"]["label"] == "renamed"

        # DELETE
        r = authed_client.delete(f"{BASE}/{ENTRY_ID}")
        assert r.status_code == 200
        assert r.json()["data"] == {"id": ENTRY_ID, "deleted": True}

    assert "list" in _StubService.calls
    assert "add" in _StubService.calls
    assert "delete" in _StubService.calls


def test_patch_only_forwards_supplied_fields(authed_client):
    """A PATCH with just is_active must not also blank the label (sentinel wiring)."""
    _StubService.calls = []
    with patch(
        "src.utils.rbac_utils.is_user_admin", new_callable=AsyncMock, return_value=True
    ), patch.object(allowlist_routes, "AccountCreationAllowlistService", _StubService):
        authed_client.patch(f"{BASE}/{ENTRY_ID}", json={"is_active": True})

    assert "update:['is_active']" in _StubService.calls


def test_create_validation_error_is_422(authed_client):
    """A malformed IP surfaces the service's RextValidationException as 422."""
    from src.api.middleware.exceptions import RextValidationException

    class _RejectingService(_StubService):
        async def add_entry(self, *a, **k):
            raise RextValidationException(
                message="Invalid IP address or CIDR range",
                field_errors={"ip_address": ["not an IP"]},
            )

    with patch(
        "src.utils.rbac_utils.is_user_admin", new_callable=AsyncMock, return_value=True
    ), patch.object(allowlist_routes, "AccountCreationAllowlistService", _RejectingService):
        r = authed_client.post(BASE, json={"ip_address": "nonsense"})

    assert r.status_code == 422
