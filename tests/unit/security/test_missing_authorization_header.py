"""A signed-in route asked with no Authorization header answers 401, not 422 (rext-control#883).

Declared as a required header, its absence was a validation error, answered before the session
check ran. A dashboard tab that had been signed out underneath a form then got 422 on every call
(seen on live on 8 October 2026: a first workspace's Create, twice) and was never told to sign in.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.middleware.exceptions import RextAuthenticationException
from src.api.security import dependencies
from src.api.server import app

# Routes of both kinds: the session check alone, and a route that also reads the header itself.
SIGNED_IN_ROUTES = [
    ("GET", "/api/v1/user/profile"),
    ("GET", "/api/v1/workspaces/all"),
    ("POST", "/api/v1/workspaces/"),
    ("GET", "/api/v1/user/sessions"),
    ("POST", "/api/v1/user/logout"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("check", [dependencies.get_current_user], ids=lambda f: f.__name__)
async def test_the_session_check_refuses_a_missing_header_as_not_signed_in(check):
    with pytest.raises(RextAuthenticationException) as refused:
        await check(authorization=None, db=object())

    assert refused.value.status_code == 401
    assert refused.value.message == "Authorization header missing"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", SIGNED_IN_ROUTES)
async def test_a_signed_in_route_with_no_header_answers_401(method, path):
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
        response = await http.request(method, path, json={} if method == "POST" else None)

    assert response.status_code == 401, response.text[:200]
    assert "Authorization header missing" in response.text


@pytest.mark.asyncio
async def test_a_header_that_is_not_a_bearer_token_is_still_a_401():
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
        response = await http.get("/api/v1/user/profile", headers={"Authorization": "nonsense"})

    assert response.status_code == 401
