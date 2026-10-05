"""Testing a WordPress connection again, and crediting the persona's WordPress author.

The plugin's routes are the Rext AI plugin's (revnix/rext-wp-plugin,
includes/class-rext-ai-api.php): GET /verify and GET /authors need the API key;
/authors answers {"success": true, "data": [{"id", "username", "display_name",
"email", ...}]}, every user who can write posts.
"""

from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from src.web.wordpress import WordPressPublisher

PLUGIN = "https://example.com/wp-json/rext-ai/v1"


def _plugin_publisher(api_endpoint: str = PLUGIN) -> WordPressPublisher:
    return WordPressPublisher(
        site_url="https://example.com", api_endpoint=api_endpoint, api_key="key"
    )


def _answer(publisher: WordPressPublisher, routes: dict):
    """Answer GETs by URL suffix: a status code, a (status, json) pair, or an exception."""

    async def _get(url: str, **kwargs):
        for suffix, reply in routes.items():
            if url.endswith(suffix):
                if isinstance(reply, Exception):
                    raise reply
                status, body = reply if isinstance(reply, tuple) else (reply, {})
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"code": "rest_no_route"})

    publisher.client.get = AsyncMock(side_effect=_get)
    return publisher.client.get


# ---------------------------------------------------------------------------
# check_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_working_key_is_connected_and_the_author_list_answers():
    publisher = _plugin_publisher()
    get = _answer(publisher, {"/verify": 200, "/authors": (200, {"success": True, "data": []})})

    result = await publisher.check_connection()

    assert result["status"] == "connected"
    assert result["authors_available"] is True
    assert [c.args[0] for c in get.await_args_list] == [f"{PLUGIN}/verify", f"{PLUGIN}/authors"]


@pytest.mark.asyncio
async def test_without_a_stored_endpoint_the_plugin_default_path_is_used():
    publisher = _plugin_publisher(api_endpoint="")
    get = _answer(publisher, {"/verify": 200, "/authors": 404})

    result = await publisher.check_connection()

    assert get.await_args_list[0].args[0] == f"{PLUGIN}/verify"
    assert result["status"] == "connected"
    assert result["authors_available"] is False


@pytest.mark.parametrize(
    ("reply", "status"),
    [
        (401, "invalid_credentials"),
        (403, "invalid_credentials"),
        (404, "plugin_missing"),
        (503, "plugin_disabled"),
        (429, "rate_limited"),
        (500, "error"),
        (httpx.ConnectError("refused"), "unreachable"),
        (httpx.ReadTimeout("slow"), "unreachable"),
    ],
)
@pytest.mark.asyncio
async def test_each_failure_reads_as_a_status_with_a_message(reply, status):
    publisher = _plugin_publisher()
    _answer(publisher, {"/verify": reply})

    result = await publisher.check_connection()

    assert result["status"] == status
    assert result["message"]
    assert result["authors_available"] is None


@pytest.mark.asyncio
async def test_an_application_password_is_checked_against_wordpress_core():
    publisher = WordPressPublisher(
        site_url="https://example.com", username="editor", app_password="abcd efgh"
    )
    get = _answer(publisher, {"/wp/v2/users/me": 200})

    result = await publisher.check_connection()

    assert get.await_args_list[0].args[0] == "https://example.com/wp-json/wp/v2/users/me"
    assert result == {
        "status": "connected",
        "message": "Connected: WordPress accepted the application password.",
        "authors_available": None,
    }


# ---------------------------------------------------------------------------
# resolve_author_id with the plugin's author list
# ---------------------------------------------------------------------------

AUTHORS = {
    "success": True,
    "data": [
        {"id": 3, "username": "jdoe", "display_name": "Jane Doe", "email": "jane@example.com"},
        {"id": 7, "username": "sam", "display_name": "Sam Lee", "email": "sam@example.com"},
    ],
}


@pytest.mark.asyncio
async def test_the_persona_is_matched_by_display_name_in_the_plugin_list():
    publisher = _plugin_publisher()
    get = _answer(publisher, {"/authors": (200, AUTHORS)})

    assert await publisher.resolve_author_id("Jane Doe") == 3
    assert get.await_args_list[0].args[0] == f"{PLUGIN}/authors"


@pytest.mark.asyncio
async def test_the_persona_is_matched_by_email_in_the_plugin_list():
    publisher = _plugin_publisher()
    _answer(publisher, {"/authors": (200, AUTHORS)})

    assert await publisher.resolve_author_id("Samuel Lee", "SAM@example.com") == 7


@pytest.mark.asyncio
async def test_the_only_author_on_the_site_is_not_credited_for_another_name():
    publisher = _plugin_publisher()
    only = {"success": True, "data": [AUTHORS["data"][0]]}
    _answer(publisher, {"/authors": (200, only)})

    assert await publisher.resolve_author_id("Someone Else") is None


@pytest.mark.asyncio
async def test_an_older_plugin_without_authors_falls_back_to_the_core_search():
    publisher = _plugin_publisher()
    get = _answer(
        publisher,
        {"/authors": 404, "/wp/v2/users": (200, [{"id": 9, "name": "J. Doe", "slug": "jd"}])},
    )

    # A single search hit is the user WordPress itself matched.
    assert await publisher.resolve_author_id("Jane Doe") == 9
    assert get.await_args_list[1].args[0] == "https://example.com/wp-json/wp/v2/users"
    assert get.await_args_list[1].kwargs["params"] == {"search": "Jane Doe", "per_page": 20}


# ---------------------------------------------------------------------------
# POST /api/v1/integrations/wordpress/{site_id}/test
# ---------------------------------------------------------------------------


class _FakePublisher:
    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakePublisher.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def check_connection(self):
        return {"status": "invalid_credentials", "message": "refused", "authors_available": None}


async def _post_test(monkeypatch, site, *, check_addresses=False):
    from src.api.database.async_database import get_async_db
    from src.api.security.dependencies import get_current_user
    from src.api.server import app

    workspace_id = uuid4()
    routes = "src.api.routes.integrations.wordpress"
    monkeypatch.setattr(
        f"{routes}.resolve_and_verify_workspace",
        AsyncMock(return_value=(SimpleNamespace(id=workspace_id), None)),
    )
    monkeypatch.setattr(f"{routes}.WordPressPublisher", _FakePublisher)
    if not check_addresses:
        # example.com would be resolved through DNS; the guard has its own test below.
        monkeypatch.setattr(f"{routes}.validate_url_for_ssrf", lambda url: url)
    _FakePublisher.instances = []

    class _DB:
        async def execute(self, _query):
            return SimpleNamespace(scalar_one_or_none=lambda: site)

        async def commit(self):
            return None

        async def rollback(self):
            return None

    async def override_get_db() -> AsyncGenerator[_DB, None]:
        yield _DB()

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(uuid4())}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.post(
                f"/api/v1/integrations/wordpress/{site.id}/test",
                params={"workspace_id": str(workspace_id)},
            )
    finally:
        app.dependency_overrides.clear()


def _site():
    return SimpleNamespace(
        id=uuid4(),
        integration_type="wordpress",
        site_url="https://example.com",
        api_endpoint=PLUGIN,
        username=None,
        app_password=None,
        api_key=None,
    )


@pytest.mark.asyncio
async def test_the_endpoint_tests_the_stored_credentials(monkeypatch, allow_permissions):
    site = _site()
    site.api_key = "stored-key"

    response = await _post_test(monkeypatch, site)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["site_id"] == str(site.id)
    assert data["ok"] is False
    assert data["status"] == "invalid_credentials"
    assert data["checked_at"]
    (publisher,) = _FakePublisher.instances
    assert publisher.kwargs["api_key"] == "stored-key"
    assert publisher.kwargs["site_url"] == "https://example.com"


@pytest.mark.asyncio
async def test_a_connection_without_credentials_is_not_sent_anywhere(
    monkeypatch, allow_permissions
):
    response = await _post_test(monkeypatch, _site())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ok"] is False
    assert data["status"] == "no_credentials"
    assert _FakePublisher.instances == []


@pytest.mark.asyncio
async def test_a_private_address_is_refused_before_any_request(monkeypatch, allow_permissions):
    site = _site()
    site.api_key = "stored-key"
    site.site_url = "http://127.0.0.1:8080"
    site.api_endpoint = "http://127.0.0.1:8080/wp-json/rext-ai/v1"

    response = await _post_test(monkeypatch, site, check_addresses=True)

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "blocked_address"
    assert _FakePublisher.instances == []
