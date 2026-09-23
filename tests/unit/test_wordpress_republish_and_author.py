"""Republishing edits the existing post, and the chosen author is credited.

These mock ``client.request`` — the single call every WordPress request goes
through (``WordPressPublisher._request_with_retry``) — so both the URL a publish
is sent to and the payload it carries are visible to the assertions.
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from src.api.schema.content_schema import ContentCreate
from src.web.wordpress import WordPressPublisher


def _publisher() -> WordPressPublisher:
    return WordPressPublisher(
        site_url="https://example.com",
        username="user",
        app_password="pass",
    )


def _route(publisher: WordPressPublisher, *, post_json: dict, users: list | None = None):
    """Answer every WordPress call this publisher makes.

    GET /users -> the site's user list (author lookup)
    GET anything else -> an empty list (categories/tags)
    POST -> the published/updated post
    """

    async def _request(method: str, url: str, **kwargs):
        if method.upper() == "POST":
            return httpx.Response(200, json=post_json)
        if "/users" in url:
            return httpx.Response(200, json=users or [])
        return httpx.Response(200, json=[])

    async def _get(url: str, **kwargs):
        return await _request("GET", url, **kwargs)

    publisher.client.request = AsyncMock(side_effect=_request)
    publisher.client.get = AsyncMock(side_effect=_get)
    return publisher.client.request


def _article() -> ContentCreate:
    return ContentCreate(title="Republished article", body_html="<p>Body</p>")


@pytest.mark.asyncio
async def test_publish_without_a_post_id_creates_a_new_post():
    publisher = _publisher()
    request = _route(publisher, post_json={"id": 41, "status": "publish"})

    result = await publisher.publish_post(_article(), status="publish")

    posted_url = request.await_args_list[-1].args[1]
    assert posted_url == "https://example.com/wp-json/wp/v2/posts"
    assert result["updated_existing_post"] is False


@pytest.mark.asyncio
async def test_republish_updates_the_existing_post_instead_of_creating_another():
    publisher = _publisher()
    request = _route(publisher, post_json={"id": 41, "status": "publish"})

    result = await publisher.publish_post(_article(), status="publish", post_id=41)

    posted_url = request.await_args_list[-1].args[1]
    assert posted_url == "https://example.com/wp-json/wp/v2/posts/41"
    assert result["post_id"] == 41
    assert result["updated_existing_post"] is True


@pytest.mark.asyncio
async def test_selected_author_is_resolved_and_sent_to_wordpress():
    publisher = _publisher()
    request = _route(
        publisher,
        post_json={"id": 42, "status": "publish", "author": 7},
        users=[
            {"id": 3, "name": "Someone Else", "slug": "someone-else"},
            {"id": 7, "name": "Sara Ortiz", "slug": "sara-ortiz"},
        ],
    )

    result = await publisher.publish_post(_article(), status="publish", author_name="Sara Ortiz")

    payload = request.await_args_list[-1].kwargs["json"]
    assert payload["author"] == 7
    assert result["author_id"] == 7
    assert result["author_applied"] is True


@pytest.mark.asyncio
async def test_author_is_matched_by_email_when_the_name_differs():
    publisher = _publisher()
    request = _route(
        publisher,
        post_json={"id": 43, "status": "publish", "author": 9},
        users=[{"id": 9, "name": "S. Ortiz", "email": "sara@example.com"}],
    )

    await publisher.publish_post(
        _article(),
        status="publish",
        author_name="Sara Ortiz",
        author_email="sara@example.com",
    )

    assert request.await_args_list[-1].kwargs["json"]["author"] == 9


@pytest.mark.asyncio
async def test_unknown_author_publishes_under_the_connected_account():
    """A persona with no WordPress user must not fail the publish."""
    publisher = _publisher()
    request = _route(publisher, post_json={"id": 44, "status": "publish"}, users=[])

    result = await publisher.publish_post(_article(), status="publish", author_name="Nobody Here")

    assert "author" not in request.await_args_list[-1].kwargs["json"]
    assert result["success"] is True
    assert result["author_id"] is None


@pytest.mark.asyncio
async def test_publish_reports_when_wordpress_ignores_the_selected_author():
    """The post is still published — the mismatch is reported, not raised."""
    publisher = _publisher()
    _route(
        publisher,
        post_json={"id": 45, "status": "publish", "author": 1},
        users=[{"id": 7, "name": "Sara Ortiz"}],
    )

    result = await publisher.publish_post(_article(), status="publish", author_name="Sara Ortiz")

    assert result["success"] is True
    assert result["author_applied"] is False


_POST_REQUEST = httpx.Request("GET", "https://example.com/wp-json/wp/v2/posts/41")


@pytest.mark.asyncio
async def test_existing_post_is_confirmed_before_it_is_updated():
    publisher = _publisher()
    publisher.client.get = AsyncMock(
        return_value=httpx.Response(
            200, json={"id": 41, "status": "publish"}, request=_POST_REQUEST
        )
    )

    assert await publisher.confirm_existing_post(41) == 41


@pytest.mark.asyncio
async def test_a_post_deleted_on_the_site_falls_back_to_creating_a_new_one():
    publisher = _publisher()
    publisher.client.get = AsyncMock(
        return_value=httpx.Response(404, json={}, request=_POST_REQUEST)
    )

    assert await publisher.confirm_existing_post(41) is None
    assert await publisher.confirm_existing_post(None) is None
