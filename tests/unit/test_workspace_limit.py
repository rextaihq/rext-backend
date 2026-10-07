"""The plan's workspace limit holds on the server (G72, rext-control#591): one gate,
`check_workspace_limit()`, refuses a workspace beyond the plan's `max_workspaces` with a 429
and the plan's sentence, which the dashboard shows. A super admin and a plan without a limit
aren't limited; no subscription means the free tier's one workspace."""

from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from src.api.middleware import usage_limiter

USER = str(uuid4())
AT_THE_LIMIT = "Workspace limit reached (1/1). Please upgrade your plan to create more workspaces."


def _plan(max_workspaces):
    return SimpleNamespace(id=uuid4(), max_workspaces=max_workspaces)


@pytest.fixture
def account(monkeypatch):
    """The caller's plan, live workspaces and role, as the gate reads them."""
    state = {"plan": _plan(1), "workspaces": 1, "super_admin": False}

    async def subscription_and_plan(db, user_id):
        plan = state["plan"]
        return (SimpleNamespace(id=uuid4()), plan) if plan else (None, None)

    async def count(db, user_id):
        return state["workspaces"]

    async def super_admin(db, user_id):
        return state["super_admin"]

    monkeypatch.setattr(
        usage_limiter, "_get_user_subscription_and_plan_async", subscription_and_plan
    )
    monkeypatch.setattr(usage_limiter, "_live_workspace_count", count)
    monkeypatch.setattr(usage_limiter.rbac_utils, "is_user_super_admin", super_admin)
    return state


async def _gate() -> None:
    await usage_limiter.WorkspaceLimitChecker()(
        request=None, current_user={"identity": USER}, db=object()
    )


@pytest.mark.asyncio
async def test_a_second_workspace_at_the_limit_is_refused_through_the_api(account, monkeypatch):
    from src.api.database.async_database import get_async_db
    from src.api.security.dependencies import get_current_user
    from src.api.server import app

    # Nothing past the gate may run: the address check and the create would fail the test.
    monkeypatch.setattr(
        "src.api.routes.workspaces.workspace_core.check_website_reachable",
        AsyncMock(side_effect=AssertionError("the gate let the create through")),
    )

    async def override_db() -> AsyncGenerator[object, None]:
        yield object()

    app.dependency_overrides[get_async_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": USER}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/workspaces/",
                json={"name": "Second", "url": "https://example.com", "timezone": "UTC"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 429
    assert response.json()["message"] == AT_THE_LIMIT


@pytest.mark.asyncio
async def test_under_the_limit_a_workspace_is_allowed(account):
    account.update(plan=_plan(3), workspaces=2)
    await _gate()


@pytest.mark.asyncio
@pytest.mark.parametrize("unlimited", [-1, None])
async def test_a_plan_without_a_limit_is_not_limited(account, unlimited):
    account.update(plan=_plan(unlimited), workspaces=40)
    await _gate()


@pytest.mark.asyncio
async def test_a_super_admin_is_not_limited(account):
    account.update(plan=_plan(1), workspaces=5, super_admin=True)
    await _gate()


@pytest.mark.asyncio
async def test_without_a_subscription_the_free_tier_has_one_workspace(account):
    account.update(plan=None, workspaces=0)
    await _gate()

    account.update(workspaces=1)
    with pytest.raises(HTTPException) as refused:
        await _gate()
    assert refused.value.status_code == 429
    assert refused.value.detail.startswith("Workspace limit reached (1/1).")


def test_creating_a_workspace_has_one_limit_gate():
    from src.api.dependencies.feature_gate import RequireFeature
    from src.api.routes.workspaces.workspace_core import router

    route = next(r for r in router.routes if r.path == "/" and "POST" in r.methods)
    calls = [d.call for d in route.dependant.dependencies]
    assert any(isinstance(c, usage_limiter.WorkspaceLimitChecker) for c in calls)
    assert not any(isinstance(c, RequireFeature) for c in calls)
