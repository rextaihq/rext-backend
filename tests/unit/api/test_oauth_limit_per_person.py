"""Signing in with Google or GitHub is limited per person, not per calling address
(rext-control#892).

The dashboard's server makes that call, so the backend sees the dashboard server's address for
every such sign-in. The limiter adds the email to its key for sign-in routes, but looked for
`email` or `email_address`, and this route's body names it `provider_email`: every Google and
GitHub sign-in through one address shared one allowance of ten in five minutes.
"""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI

from src.api.middleware import rate_limiter as rate_limiter_module
from src.api.middleware.rate_limiter import OAUTH_LIMIT, oauth_rate_limit

DASHBOARD_SERVER = ("198.51.100.20", 51000)
ROUTE = "/api/v1/user/oauth/login"


@pytest.fixture
def http(monkeypatch):
    """The route's own limiter on a bare app, counted in memory, every call from one address."""
    monkeypatch.setattr(rate_limiter_module, "cache", SimpleNamespace(redis=None))
    app = FastAPI()

    @app.post(ROUTE, dependencies=[Depends(oauth_rate_limit())])
    async def oauth_login():
        return {"ok": True}

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=DASHBOARD_SERVER),
        base_url="http://testserver",
    )


def _sign_in(email: str | None) -> dict:
    body = {"provider": "google", "provider_account_id": "an-account"}
    if email is not None:
        body["provider_email"] = email
    return body


@pytest.mark.asyncio
async def test_different_people_through_one_address_do_not_share_an_allowance(http):
    async with http:
        answers = [
            (await http.post(ROUTE, json=_sign_in(f"person{n}@example.com"))).status_code
            for n in range(OAUTH_LIMIT.requests * 3)
        ]

    assert set(answers) == {200}


@pytest.mark.asyncio
async def test_one_person_is_still_limited(http):
    async with http:
        answers = [
            (await http.post(ROUTE, json=_sign_in("ana@example.com"))).status_code
            for _ in range(OAUTH_LIMIT.requests + 1)
        ]
        # Another person, the same address, the same minute: not held up by the first.
        other = await http.post(ROUTE, json=_sign_in("ben@example.com"))

    assert answers[:-1] == [200] * OAUTH_LIMIT.requests
    assert answers[-1] == 429
    assert other.status_code == 200


@pytest.mark.asyncio
async def test_the_same_address_written_differently_is_one_person(http):
    async with http:
        for _ in range(OAUTH_LIMIT.requests):
            await http.post(ROUTE, json=_sign_in("Ana@Example.com "))
        refused = await http.post(ROUTE, json=_sign_in("ana@example.com"))

    assert refused.status_code == 429


@pytest.mark.asyncio
async def test_a_call_with_no_email_is_still_counted_by_its_address(http):
    async with http:
        answers = [
            (await http.post(ROUTE, json=_sign_in(None))).status_code
            for _ in range(OAUTH_LIMIT.requests + 1)
        ]

    assert answers[-1] == 429
