"""
The incident banner (FB2.36, #728): its state in Redis and its three routes.

Redis is a stand-in here, with the three calls the service makes. The caller's permissions are
stubbed underneath the real require_permissions, as in test_rbac_route_authorization.py.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Callable
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextExternalServiceException
from src.api.security.dependencies import get_current_user
from src.api.server import app
from src.services import incident_banner_service
from src.services.incident_banner_service import (
    BANNER_KEY,
    NO_BANNER,
    clear_banner,
    read_banner,
    set_banner,
)

NOW = datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc)
MESSAGE = "Article writing is slow right now. We're on it."


class FakeRedis:
    """The cache client's get and set, and the Redis client's own delete, over a dict."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.ttls: dict[str, int] = {}
        self.reachable = True
        self.delete_fails = False
        # The service deletes through the Redis client itself, which this object also plays.
        self.redis = self

    @property
    def is_enabled(self) -> bool:
        return self.reachable

    async def get(self, key: str) -> Any:
        return self.values.get(key) if self.reachable else None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self.reachable:
            return False
        # As the real client stores it: JSON, so times come back as text.
        self.values[key] = json.loads(json.dumps(value, default=str))
        self.ttls[key] = ttl
        return True

    async def delete(self, key: str) -> int:
        if self.delete_fails:
            raise ConnectionError("redis went away")
        return 1 if self.values.pop(key, None) is not None else 0


@pytest.fixture
def redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(incident_banner_service, "cache", fake)
    return fake


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_there_is_no_banner_until_one_is_switched_on(redis: FakeRedis):
    assert await read_banner() == NO_BANNER


@pytest.mark.asyncio
async def test_a_banner_shows_until_its_end_time_and_redis_expires_it_then(redis: FakeRedis):
    shown = await set_banner(MESSAGE, ["generation"], duration_minutes=90, now=NOW)

    assert shown["active"] is True
    assert shown["expires_at"] == NOW + timedelta(minutes=90)
    # The key's own expiry is the banner's end time.
    assert redis.ttls[BANNER_KEY] == 90 * 60

    read = await read_banner(now=NOW + timedelta(minutes=89))
    assert read == {
        "active": True,
        "message": MESSAGE,
        "areas": ["generation"],
        "started_at": NOW,
        "expires_at": NOW + timedelta(minutes=90),
    }
    # Past its end time there is none, even if the key were still there.
    assert await read_banner(now=NOW + timedelta(minutes=90)) == NO_BANNER


@pytest.mark.asyncio
async def test_a_new_banner_replaces_the_one_showing(redis: FakeRedis):
    await set_banner(MESSAGE, ["generation"], duration_minutes=60, now=NOW)
    await set_banner("Publishing to WordPress is failing.", ["publishing"], 30, now=NOW)

    read = await read_banner(now=NOW)
    assert read["message"] == "Publishing to WordPress is failing."
    assert read["areas"] == ["publishing"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored",
    [
        "a string, not a banner",
        ["a", "list"],
        {"expires_at": "2026-10-09T06:00:00+00:00"},
        {"message": "   ", "expires_at": "2026-10-09T06:00:00+00:00"},
        {"message": MESSAGE},
        {"message": MESSAGE, "expires_at": "tomorrow"},
        {"message": MESSAGE, "expires_at": 1791460000},
    ],
)
async def test_a_stored_value_that_is_not_a_banner_shows_nothing(redis: FakeRedis, stored: Any):
    redis.values[BANNER_KEY] = stored
    assert await read_banner(now=NOW) == NO_BANNER


@pytest.mark.asyncio
async def test_areas_that_are_not_text_are_left_out(redis: FakeRedis):
    redis.values[BANNER_KEY] = {
        "message": MESSAGE,
        "areas": ["generation", 7, None],
        "expires_at": "2026-10-09T06:00:00+00:00",
    }
    assert (await read_banner(now=NOW))["areas"] == ["generation"]


@pytest.mark.asyncio
async def test_redis_away_means_no_banner_and_a_read_that_never_fails(redis: FakeRedis):
    await set_banner(MESSAGE, [], duration_minutes=60, now=NOW)
    redis.reachable = False
    assert await read_banner(now=NOW) == NO_BANNER

    async def broken(_key: str) -> Any:
        raise RuntimeError("the client itself broke")

    redis.reachable = True
    redis.get = broken  # type: ignore[method-assign]
    assert await read_banner(now=NOW) == NO_BANNER


@pytest.mark.asyncio
async def test_switching_on_says_so_when_redis_does_not_take_it(redis: FakeRedis):
    redis.reachable = False
    with pytest.raises(RextExternalServiceException) as refused:
        await set_banner(MESSAGE, [], duration_minutes=60, now=NOW)
    assert refused.value.status_code == 503
    assert redis.values == {}


@pytest.mark.asyncio
async def test_switching_off_removes_it_and_says_whether_one_was_showing(redis: FakeRedis):
    await set_banner(MESSAGE, [], duration_minutes=60, now=NOW)
    assert await clear_banner() is True
    assert await read_banner(now=NOW) == NO_BANNER
    assert await clear_banner() is False


@pytest.mark.asyncio
async def test_switching_off_says_so_when_it_could_not(redis: FakeRedis):
    await set_banner(MESSAGE, [], duration_minutes=60, now=NOW)

    # A failed delete is not "none was showing": the banner is still on every page.
    redis.delete_fails = True
    with pytest.raises(RextExternalServiceException) as failed:
        await clear_banner()
    assert failed.value.status_code == 503
    assert (await read_banner(now=NOW))["active"] is True

    redis.delete_fails = False
    redis.reachable = False
    with pytest.raises(RextExternalServiceException):
        await clear_banner()


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------


@pytest.fixture
def grant(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """A signed-in caller who is no super admin, over a mock DB; grant(*perms) sets what they hold."""
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

    _grant()
    yield _grant
    app.dependency_overrides.clear()


@pytest.fixture
def audit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    written = AsyncMock()
    monkeypatch.setattr(
        "src.api.routes.status.incident_banner_routes.create_audit_log_async", written
    )
    return written


async def _call(
    method: str,
    url: str,
    json: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.request(method, url, json=json, headers=headers)


READ = "/api/v1/status/banner"
ADMIN = "/api/v1/admin/status/banner"


@pytest.mark.asyncio
async def test_any_signed_in_user_reads_the_banner_and_gets_none_by_default(
    redis: FakeRedis, grant
):
    response = await _call("GET", READ)
    assert response.status_code == 200
    assert response.json()["data"] == {
        "active": False,
        "message": None,
        "areas": [],
        "started_at": None,
        "expires_at": None,
    }


@pytest.mark.asyncio
async def test_the_read_still_answers_none_when_redis_is_away(redis: FakeRedis, grant):
    redis.reachable = False
    response = await _call("GET", READ)
    assert response.status_code == 200
    assert response.json()["data"]["active"] is False


@pytest.mark.asyncio
async def test_the_banner_is_not_read_without_a_session(redis: FakeRedis):
    await set_banner(MESSAGE, [], duration_minutes=60)

    # The auth dependency's own answers: no Authorization header at all, and one that is no token.
    missing = await _call("GET", READ)
    assert missing.status_code == 422
    forged = await _call("GET", READ, headers={"Authorization": "Bearer not-a-token"})
    assert forged.status_code == 401
    for response in (missing, forged):
        assert MESSAGE not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["PUT", "DELETE"])
async def test_switching_it_needs_security_manage(redis: FakeRedis, grant, audit, method: str):
    grant("security.read", "admin.access")
    body = {"message": MESSAGE} if method == "PUT" else None
    response = await _call(method, ADMIN, json=body)
    assert response.status_code == 403
    assert redis.values == {}
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_super_admin_switches_it_on_and_everyone_reads_it(redis: FakeRedis, grant, audit):
    grant("security.manage")
    response = await _call(
        "PUT",
        ADMIN,
        json={
            "message": "  Article writing is slow\n right now.  ",
            "areas": ["generation", "generation", "keyword_research"],
            "duration_minutes": 120,
        },
    )
    assert response.status_code == 200
    shown = response.json()["data"]
    assert shown["active"] is True
    # One line of plain text, each area once.
    assert shown["message"] == "Article writing is slow right now."
    assert shown["areas"] == ["generation", "keyword_research"]
    assert redis.ttls[BANNER_KEY] == 120 * 60

    audit.assert_awaited_once()
    assert audit.await_args.kwargs["action"] == "incident_banner.set"
    assert audit.await_args.kwargs["new_values"]["duration_minutes"] == 120

    grant()  # an ordinary signed-in user
    read = (await _call("GET", READ)).json()["data"]
    assert read["active"] is True
    assert read["message"] == "Article writing is slow right now."
    assert read["expires_at"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"message": ""},
        {"message": "   \n  "},
        {"message": "x" * 281},
        {"message": MESSAGE, "areas": ["the_weather"]},
        {"message": MESSAGE, "duration_minutes": 5},
        {"message": MESSAGE, "duration_minutes": 24 * 60 + 1},
    ],
)
async def test_a_banner_that_is_not_well_formed_is_refused(
    redis: FakeRedis, grant, audit, body: dict[str, Any]
):
    grant("security.manage")
    response = await _call("PUT", ADMIN, json=body)
    assert response.status_code == 422
    assert redis.values == {}
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_banner_shows_for_an_hour_when_no_duration_is_given(redis: FakeRedis, grant, audit):
    grant("security.manage")
    assert (await _call("PUT", ADMIN, json={"message": MESSAGE})).status_code == 200
    assert redis.ttls[BANNER_KEY] == 60 * 60


@pytest.mark.asyncio
async def test_switching_on_answers_503_when_redis_is_away(redis: FakeRedis, grant, audit):
    grant("security.manage")
    redis.reachable = False
    response = await _call("PUT", ADMIN, json={"message": MESSAGE})
    assert response.status_code == 503
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_super_admin_switches_it_off(redis: FakeRedis, grant, audit):
    grant("security.manage")
    await _call("PUT", ADMIN, json={"message": MESSAGE})
    audit.reset_mock()

    response = await _call("DELETE", ADMIN)
    assert response.status_code == 200
    assert response.json()["data"]["active"] is False
    assert audit.await_args.kwargs["action"] == "incident_banner.clear"
    assert audit.await_args.kwargs["new_values"] == {"was_showing": True}

    assert (await _call("GET", READ)).json()["data"]["active"] is False
