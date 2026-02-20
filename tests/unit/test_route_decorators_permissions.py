import pytest
from src.api.middleware.exceptions import RextAuthorizationException
from src.utils.route_decorators import require_permissions


class DummyDB:
    pass


@pytest.mark.asyncio
async def test_require_permissions_denies_on_permission_checker_exception(monkeypatch):
    async def failing_check(*args, **kwargs):
        raise AssertionError("test-only assertion")

    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", failing_check)

    @require_permissions("user.read", workspace_scoped=False)
    async def protected_route(user=None, db=None):
        return {"ok": True}

    with pytest.raises(RextAuthorizationException) as exc:
        await protected_route(user={"identity": "123e4567-e89b-12d3-a456-426614174000"}, db=DummyDB())

    assert "Permission verification failed" in str(exc.value)