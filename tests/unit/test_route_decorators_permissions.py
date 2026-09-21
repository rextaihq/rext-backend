from uuid import uuid4

import pytest

from src.api.middleware.exceptions import RextAuthorizationException
from src.utils.route_decorators import require_permissions


class StubDB:
    _executed = True


@pytest.mark.asyncio
async def test_require_permissions_denies_even_when_db_has_executed_attr(monkeypatch):
    async def deny_permissions(*args, **kwargs):
        return False

    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", deny_permissions)

    @require_permissions("user.read", workspace_scoped=False)
    async def protected_endpoint(*, user, db):
        return {"ok": True}

    with pytest.raises(RextAuthorizationException):
        await protected_endpoint(user={"identity": str(uuid4())}, db=StubDB())


@pytest.mark.asyncio
async def test_require_permissions_allows_when_checker_allows(monkeypatch):
    async def allow_permissions(*args, **kwargs):
        return True

    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", allow_permissions)

    @require_permissions("user.read", workspace_scoped=False)
    async def protected_endpoint(*, user, db):
        return {"ok": True}

    result = await protected_endpoint(user={"identity": str(uuid4())}, db=StubDB())
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_require_permissions_denies_on_permission_checker_exception(monkeypatch):
    """Task 409: Any exception during permission evaluation must be treated as denial."""

    async def failing_check(*args, **kwargs):
        raise AssertionError("test-only assertion")

    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", failing_check)

    @require_permissions("user.read", workspace_scoped=False)
    async def protected_endpoint(*, user, db):
        return {"ok": True}

    with pytest.raises(RextAuthorizationException) as exc:
        await protected_endpoint(user={"identity": str(uuid4())}, db=StubDB())

    assert "Permission verification failed" in str(exc.value)
