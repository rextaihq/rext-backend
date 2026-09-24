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


def _route(
    publisher: WordPressPublisher,
    *,
    post_json: dict,
    users: list | None = None,
    create_user: httpx.Response | None = None,
):
    """Answer every WordPress call this publisher makes.

    GET /users -> the site's user list (author lookup)
    GET anything else -> an empty list (categories/tags)
    POST /users -> ``create_user`` (default: WordPress refuses, 403)
    POST anything else -> the published/updated post
    """

    async def _request(method: str, url: str, **kwargs):
        if method.upper() == "POST":
            if url.endswith("/wp/v2/users"):
                return create_user or httpx.Response(403, json={"code": "rest_cannot_create_user"})
            return httpx.Response(200, json=post_json)
        if "/users" in url:
            return httpx.Response(200, json=users or [])
        return httpx.Response(200, json=[])

    async def _get(url: str, **kwargs):
        return await _request("GET", url, **kwargs)

    publisher.client.request = AsyncMock(side_effect=_request)
    publisher.client.get = AsyncMock(side_effect=_get)
    return publisher.client.request


def _post_payload(request) -> dict:
    """The JSON of the last request sent to /posts."""
    posts = [c for c in request.await_args_list if "/posts" in c.args[1]]
    return posts[-1].kwargs["json"]


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
    """A persona the site won't create a user for must not fail the publish."""
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


# --- Author personas with no WordPress user yet ---------------------------------


def _serve(publisher: WordPressPublisher, handler) -> None:
    """Send every request this publisher makes to ``handler(method, url, **kwargs)``."""

    async def _get(url: str, **kwargs):
        return await handler("GET", url, **kwargs)

    publisher.client.request = AsyncMock(side_effect=handler)
    publisher.client.get = AsyncMock(side_effect=_get)


@pytest.mark.asyncio
async def test_missing_author_is_created_and_credited():
    publisher = _publisher()
    request = _route(
        publisher,
        post_json={"id": 46, "status": "publish", "author": 15},
        users=[{"id": 3, "name": "Someone Else"}],
        create_user=httpx.Response(201, json={"id": 15, "name": "Sara Ortiz"}),
    )

    result = await publisher.publish_post(
        _article(),
        status="publish",
        author_name="Sara Ortiz",
        author_email="sara@example.com",
        author_bio="Writes about gardens.",
    )

    created = next(c for c in request.await_args_list if c.args[1].endswith("/wp/v2/users"))
    user = created.kwargs["json"]
    assert user["name"] == "Sara Ortiz"
    assert user["email"] == "sara@example.com"
    assert user["description"] == "Writes about gardens."
    assert user["roles"] == ["author"]
    assert _post_payload(request)["author"] == 15
    assert result["author_created"] is True
    assert result["author_applied"] is True


@pytest.mark.asyncio
async def test_a_near_miss_name_is_not_credited_a_new_user_is_created():
    """ "Sara Ortiz Smith" may be someone else; crediting them is worse than creating."""
    publisher = _publisher()
    request = _route(
        publisher,
        post_json={"id": 47, "status": "publish", "author": 16},
        users=[{"id": 3, "name": "Sara Ortiz Smith"}],
        create_user=httpx.Response(201, json={"id": 16}),
    )

    await publisher.publish_post(_article(), status="publish", author_name="Sara Ortiz")

    assert _post_payload(request)["author"] == 16


@pytest.mark.asyncio
async def test_persona_without_email_gets_a_stable_address_on_the_site_domain():
    publisher = _publisher()
    request = _route(
        publisher,
        post_json={"id": 48, "status": "publish", "author": 17},
        create_user=httpx.Response(201, json={"id": 17}),
    )

    await publisher.publish_post(_article(), status="publish", author_name="Sara Ortiz")

    created = next(c for c in request.await_args_list if c.args[1].endswith("/wp/v2/users"))
    assert created.kwargs["json"]["username"] == "sara_ortiz"
    assert created.kwargs["json"]["email"] == "sara_ortiz@example.com"


@pytest.mark.asyncio
async def test_existing_email_resolves_to_that_user_instead_of_failing():
    """The lookup missed the user (e.g. not listable); the create conflict finds them."""
    publisher = _publisher()
    user = {"id": 21, "name": "S. Ortiz", "email": "sara@example.com"}
    conflicted = False

    async def _request(method: str, url: str, **kwargs):
        nonlocal conflicted
        if method.upper() == "POST" and url.endswith("/wp/v2/users"):
            conflicted = True
            return httpx.Response(400, json={"code": "existing_user_email"})
        if method.upper() == "POST":
            return httpx.Response(200, json={"id": 49, "status": "publish", "author": 21})
        if "/users" in url:
            # Found only by the search the conflict triggers.
            return httpx.Response(200, json=[user] if conflicted else [])
        return httpx.Response(200, json=[])

    _serve(publisher, _request)

    result = await publisher.publish_post(
        _article(), status="publish", author_name="Sara Ortiz", author_email="sara@example.com"
    )

    assert _post_payload(publisher.client.request)["author"] == 21
    assert result["author_created"] is False


@pytest.mark.asyncio
async def test_taken_login_retries_with_a_distinct_one():
    publisher = _publisher()
    responses = [
        httpx.Response(400, json={"code": "existing_user_login"}),
        httpx.Response(201, json={"id": 22}),
    ]

    async def _request(method: str, url: str, **kwargs):
        if method.upper() == "POST" and url.endswith("/wp/v2/users"):
            return responses.pop(0)
        if method.upper() == "POST":
            return httpx.Response(200, json={"id": 50, "status": "publish", "author": 22})
        return httpx.Response(200, json=[])

    _serve(publisher, _request)

    await publisher.publish_post(_article(), status="publish", author_name="Sara Ortiz")

    logins = [
        c.kwargs["json"]["username"]
        for c in publisher.client.request.await_args_list
        if c.args[1].endswith("/wp/v2/users") and c.args[0] == "POST"
    ]
    assert logins[0] == "sara_ortiz"
    assert logins[1].startswith("sara_ortiz_") and logins[1] != "sara_ortiz"
    assert _post_payload(publisher.client.request)["author"] == 22


@pytest.mark.asyncio
async def test_renamed_persona_keeps_the_user_it_was_credited_to():
    publisher = _publisher()
    request = _route(
        publisher,
        post_json={"id": 51, "status": "publish", "author": 7},
        users=[{"id": 7, "name": "Sara Ortiz"}],
    )

    await publisher.publish_post(
        _article(), status="publish", author_name="Sara O. Ramirez", author_user_id=7
    )

    assert _post_payload(request)["author"] == 7
    assert not any(
        c.args[0] == "POST" and c.args[1].endswith("/wp/v2/users") for c in request.await_args_list
    )


def _plugin_publisher(**kwargs) -> WordPressPublisher:
    return WordPressPublisher(
        site_url="https://example.com",
        api_endpoint="https://example.com/wp-json/rext-ai/v1",
        api_key="rext_test",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_plugin_finds_or_creates_the_author_with_just_the_api_key():
    publisher = _plugin_publisher()

    async def _request(method: str, url: str, **kwargs):
        if method.upper() == "POST" and url.endswith("/authors"):
            return httpx.Response(201, json={"id": 30, "created": True})
        if method.upper() == "POST":
            return httpx.Response(200, json={"id": 52, "status": "publish", "author": 30})
        return httpx.Response(200, json=[])

    _serve(publisher, _request)

    result = await publisher.publish_post(
        _article(),
        status="publish",
        author_name="Sara Ortiz",
        author_email="sara@example.com",
        author_bio="Writes about gardens.",
        author_avatar_url="https://cdn.example.com/sara.png",
        author_persona_id="p-1",
    )

    upsert = next(
        c for c in publisher.client.request.await_args_list if c.args[1].endswith("/authors")
    )
    assert upsert.kwargs["json"] == {
        "persona_id": "p-1",
        "display_name": "Sara Ortiz",
        "email": "sara@example.com",
        "bio": "Writes about gardens.",
        "avatar_url": "https://cdn.example.com/sara.png",
        "role": "author",
    }
    payload = _post_payload(publisher.client.request)
    assert payload["author"] == 30
    assert payload["post_author"] == 30
    assert result["author_created"] is True


@pytest.mark.asyncio
async def test_older_plugin_without_upsert_still_matches_listed_authors():
    publisher = _plugin_publisher()

    async def _request(method: str, url: str, **kwargs):
        if method.upper() == "POST" and url.endswith("/authors"):
            return httpx.Response(404, json={"code": "rest_no_route"})
        if method.upper() == "POST":
            return httpx.Response(200, json={"id": 53, "status": "publish", "author": 8})
        if url.endswith("/authors"):
            return httpx.Response(200, json={"data": [{"ID": 8, "display_name": "Sara Ortiz"}]})
        return httpx.Response(200, json=[])

    _serve(publisher, _request)

    result = await publisher.publish_post(_article(), status="publish", author_name="Sara Ortiz")

    assert _post_payload(publisher.client.request)["author"] == 8
    assert result["author_created"] is False


@pytest.mark.asyncio
async def test_older_plugin_without_credentials_publishes_under_the_connected_account():
    publisher = _plugin_publisher()

    async def _request(method: str, url: str, **kwargs):
        if method.upper() == "POST" and url.endswith("/authors"):
            return httpx.Response(404, json={"code": "rest_no_route"})
        if method.upper() == "POST":
            return httpx.Response(200, json={"id": 54, "status": "publish"})
        return httpx.Response(200, json=[])

    _serve(publisher, _request)

    result = await publisher.publish_post(_article(), status="publish", author_name="Sara Ortiz")

    assert "author" not in _post_payload(publisher.client.request)
    assert result["success"] is True
    assert result["author_id"] is None
