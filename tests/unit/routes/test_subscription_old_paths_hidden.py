"""The live dashboard still calls GET /subscriptions/my-subscription and GET /subscriptions/portal
until the release that moves it to /current and the POST. Both keep answering, but stay out of
the OpenAPI spec, which has one operation per route for the dashboard's generated types."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.server import app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/subscriptions/my-subscription"),
        ("GET", "/api/v1/subscriptions/current"),
        ("GET", "/api/v1/subscriptions/portal"),
        ("POST", "/api/v1/subscriptions/portal"),
    ],
)
async def test_the_old_paths_still_answer(method, path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, path)

    # No login: refused before the handler runs (an unknown path is 404, a wrong method 405).
    assert response.status_code not in (404, 405)


def test_the_spec_has_one_operation_per_route():
    paths = app.openapi()["paths"]

    assert "/api/v1/subscriptions/my-subscription" not in paths
    assert set(paths["/api/v1/subscriptions/current"]) == {"get"}
    assert set(paths["/api/v1/subscriptions/portal"]) == {"post"}
