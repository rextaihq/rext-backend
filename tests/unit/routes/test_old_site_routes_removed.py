"""One WordPress API: the dashboard manages sites through /api/v1/integrations/wordpress/,
and the older routes that did the same, or published to one site directly, are gone."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.server import app

SITE, CONTENT, WORKSPACE = uuid4(), uuid4(), uuid4()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/content/sites/list"),
        ("POST", "/api/v1/content/sites/connect"),
        ("GET", f"/api/v1/content/sites/{SITE}"),
        ("PATCH", f"/api/v1/content/sites/{SITE}"),
        ("DELETE", f"/api/v1/content/sites/{SITE}"),
        ("POST", f"/api/v1/content/sites/{SITE}/activate"),
        ("POST", f"/api/v1/content/sites/{SITE}/deactivate"),
        ("POST", f"/api/v1/content/sites/{SITE}/publish/{CONTENT}"),
        ("GET", "/api/v1/integrations/"),
        ("POST", f"/api/v1/integrations/wordpress/{SITE}/publish/{CONTENT}"),
    ],
)
async def test_the_old_site_routes_answer_not_found(method, path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, path, params={"workspace_id": str(WORKSPACE)})

    assert response.status_code == 404
