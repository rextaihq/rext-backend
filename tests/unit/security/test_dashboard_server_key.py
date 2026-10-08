"""The Google and GitHub sign-in call and the dashboard server's key (rext-control#892).

The dashboard's server makes that call and sends a key with it. A call with the key is counted
by the rate limiter per provider account; a call without it is counted by its address, as every
call was before; with `REQUIRE_DASHBOARD_SERVER_KEY` on, a call without it is refused.
"""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI

from src.api.config import get_settings
from src.api.middleware import rate_limiter as rate_limiter_module
from src.api.middleware.exceptions import RextAuthorizationException
from src.api.middleware.rate_limiter import OAUTH_LIMIT, oauth_rate_limit
from src.api.security.dashboard_server import (
    DASHBOARD_SERVER_HEADER,
    MIN_KEY_LENGTH,
    dashboard_sign_in_gate,
)

ROUTE = "/api/v1/user/oauth/login"
KEY = "k" * 64
WITH_KEY = {DASHBOARD_SERVER_HEADER: KEY}
ONE_ADDRESS = ("198.51.100.20", 51000)


@pytest.fixture
def settings(monkeypatch):
    def _set(key: str | None = None, require: bool = False) -> None:
        monkeypatch.setattr(get_settings(), "DASHBOARD_SERVER_KEY", key)
        monkeypatch.setattr(get_settings(), "REQUIRE_DASHBOARD_SERVER_KEY", require)

    _set()
    return _set


@pytest.fixture
def http(monkeypatch):
    """The route's two dependencies on a bare app, in the route's order; one calling address."""
    monkeypatch.setattr(rate_limiter_module, "cache", SimpleNamespace(redis=None))
    app = FastAPI()

    @app.exception_handler(RextAuthorizationException)
    async def _refused(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse({"message": exc.message}, status_code=exc.status_code)

    @app.post(ROUTE, dependencies=[Depends(dashboard_sign_in_gate), Depends(oauth_rate_limit())])
    async def oauth_login(body: dict):
        return {"account": body.get("provider_account_id")}

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=ONE_ADDRESS),
        base_url="http://testserver",
    )


def _sign_in(account: str | None = "account-1", email: str = "ana@example.com") -> dict:
    body = {"provider": "google", "provider_email": email}
    if account is not None:
        body["provider_account_id"] = account
    return body


async def _statuses(http, bodies, headers=None) -> list[int]:
    return [(await http.post(ROUTE, json=body, headers=headers)).status_code for body in bodies]


@pytest.mark.asyncio
async def test_with_the_key_people_signing_in_together_do_not_share_an_allowance(http, settings):
    settings(KEY)
    async with http:
        answers = await _statuses(
            http, [_sign_in(f"account-{n}") for n in range(OAUTH_LIMIT.requests * 3)], WITH_KEY
        )

    assert set(answers) == {200}


@pytest.mark.asyncio
async def test_with_the_key_one_provider_account_is_still_limited(http, settings):
    settings(KEY)
    async with http:
        # The email changes with every call: it is not what the call is counted by.
        answers = await _statuses(
            http,
            [
                _sign_in("account-1", f"other{n}@example.com")
                for n in range(OAUTH_LIMIT.requests + 1)
            ],
            WITH_KEY,
        )
        someone_else = await http.post(ROUTE, json=_sign_in("account-2"), headers=WITH_KEY)

    assert answers[:-1] == [200] * OAUTH_LIMIT.requests
    assert answers[-1] == 429
    assert someone_else.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [None, {DASHBOARD_SERVER_HEADER: "not-the-key" * 6}])
async def test_without_the_key_a_call_is_counted_by_its_address_whatever_it_names(
    http, settings, headers
):
    settings(KEY)
    async with http:
        # A different account and email every time, from one address: one allowance, as before.
        answers = await _statuses(
            http,
            [
                _sign_in(f"account-{n}", f"p{n}@example.com")
                for n in range(OAUTH_LIMIT.requests + 1)
            ],
            headers,
        )

    assert answers[:-1] == [200] * OAUTH_LIMIT.requests
    assert answers[-1] == 429


@pytest.mark.asyncio
async def test_with_no_key_set_nothing_is_a_proof(http, settings):
    settings(None)
    async with http:
        answers = await _statuses(
            http,
            [_sign_in(f"account-{n}") for n in range(OAUTH_LIMIT.requests + 1)],
            {DASHBOARD_SERVER_HEADER: ""},
        )
        named_none = await http.post(
            ROUTE, json=_sign_in("x"), headers={DASHBOARD_SERVER_HEADER: "None"}
        )

    assert answers[-1] == 429
    assert named_none.status_code == 429  # counted with the rest: not a proof either


@pytest.mark.asyncio
async def test_a_key_that_is_too_short_counts_as_not_set(http, settings):
    short = "k" * (MIN_KEY_LENGTH - 1)
    settings(short)
    async with http:
        answers = await _statuses(
            http,
            [_sign_in(f"account-{n}") for n in range(OAUTH_LIMIT.requests + 1)],
            {DASHBOARD_SERVER_HEADER: short},
        )

    assert answers[-1] == 429


@pytest.mark.asyncio
async def test_a_proven_call_that_names_no_account_is_counted_by_its_address(http, settings):
    settings(KEY)
    async with http:
        answers = await _statuses(
            http, [_sign_in(None) for _ in range(OAUTH_LIMIT.requests + 1)], WITH_KEY
        )

    assert answers[-1] == 429


@pytest.mark.asyncio
async def test_required_a_call_without_the_key_is_refused(http, settings):
    settings(KEY, require=True)
    async with http:
        bare = await http.post(ROUTE, json=_sign_in())
        wrong = await http.post(ROUTE, json=_sign_in(), headers={DASHBOARD_SERVER_HEADER: "w" * 64})
        right = await http.post(ROUTE, json=_sign_in(), headers=WITH_KEY)

    assert bare.status_code == 403
    assert wrong.status_code == 403
    assert "only possible from the Rext app" in bare.json()["message"]
    assert right.status_code == 200
    # Nothing of the key in what the caller is told.
    assert KEY not in bare.text and KEY not in wrong.text


@pytest.mark.asyncio
async def test_required_with_no_key_set_every_call_is_refused_and_the_log_says_why(
    http, settings, caplog
):
    settings(None, require=True)
    with caplog.at_level("ERROR"):
        async with http:
            answer = await http.post(ROUTE, json=_sign_in(), headers=WITH_KEY)

    assert answer.status_code == 403
    assert any("DASHBOARD_SERVER_KEY is not set" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_not_required_a_call_without_the_key_goes_through_as_before(http, settings):
    settings(KEY, require=False)
    async with http:
        answer = await http.post(ROUTE, json=_sign_in())

    assert answer.status_code == 200


def test_the_log_never_holds_the_key(settings, caplog):
    """The gate's own lines name the caller's network and nothing of either key."""
    import asyncio

    from starlette.requests import Request

    settings(KEY, require=True)
    scope = {
        "type": "http",
        "method": "POST",
        "path": ROUTE,
        "headers": [(DASHBOARD_SERVER_HEADER.lower().encode(), b"w" * 64)],
        "client": ONE_ADDRESS,
        "query_string": b"",
    }
    with caplog.at_level("INFO"), pytest.raises(RextAuthorizationException):
        asyncio.run(dashboard_sign_in_gate(Request(scope)))

    text = " ".join(r.getMessage() for r in caplog.records)
    assert KEY not in text and "w" * 64 not in text


def test_the_real_route_runs_the_gate_before_its_limit():
    from src.api.routes.users.auth import router

    route = next(r for r in router.routes if r.path.endswith("/oauth/login"))
    calls = [d.call for d in route.dependant.dependencies]
    names = [getattr(c, "__name__", type(c).__name__) for c in calls]

    assert "dashboard_sign_in_gate" in names
    assert names.index("dashboard_sign_in_gate") < names.index("EndpointRateLimiter")
