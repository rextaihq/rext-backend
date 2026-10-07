"""Removing a keyword from the caller's own Keywords library (G78, rext-control#627): the
item and the search results kept beside it go; another user's key, or one already gone, is a
404 that deletes nothing; without the workspace's content.read it's a 403."""

from types import SimpleNamespace
from typing import AsyncGenerator
from urllib.parse import quote
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from langgraph_sdk.errors import NotFoundError

ROUTE = "src.api.routes.workspaces.workspace_keyword_library"
USER, OTHER, WORKSPACE = str(uuid4()), str(uuid4()), str(uuid4())
KEY = "library_email/marketing? tools_2026-10-07T09:00:00+00:00"


def _not_found() -> NotFoundError:
    request = httpx.Request("GET", "http://langgraph/store/items")
    return NotFoundError("Item not found", response=httpx.Response(404, request=request), body=None)


class _Store:
    """The in-process store client: items by (namespace, key)."""

    def __init__(self, items):
        self.items = dict(items)

    async def get_item(self, namespace, /, key):
        try:
            return self.items[(tuple(namespace), key)]
        except KeyError:
            raise _not_found() from None

    async def delete_item(self, namespace, /, key):
        self.items.pop((tuple(namespace), key), None)


@pytest.fixture
def library(monkeypatch):
    from src.api.database.async_database import get_async_db
    from src.api.security.dependencies import get_current_user
    from src.api.server import app

    store = _Store({})
    monkeypatch.setattr("langgraph_sdk.get_client", lambda: SimpleNamespace(store=store))

    async def resolve(*, db, workspace_identifier, user):
        return SimpleNamespace(id=WORKSPACE), None

    monkeypatch.setattr(f"{ROUTE}.resolve_workspace_for_route", resolve)

    async def override_db() -> AsyncGenerator[object, None]:
        yield object()

    app.dependency_overrides[get_async_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": USER}

    async def remove(key: str = KEY):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.delete(
                f"/api/v1/workspaces/{WORKSPACE}/keyword-library/items?key={quote(key, safe='')}"
            )

    yield store, remove
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_removing_a_keyword_deletes_it_and_its_kept_results(library, allow_permissions):
    store, remove = library
    store.items = {
        (("library", USER, WORKSPACE), KEY): {"value": {"keyword": "email marketing tools"}},
        (("library_research", USER, WORKSPACE), KEY): {"value": {"serp": []}},
        (("library", USER, WORKSPACE), "library_other"): {"value": {}},
    }

    response = await remove()

    assert response.status_code == 200
    assert response.json()["data"] == {"deleted_key": KEY}
    # Only that keyword goes, with the results kept beside it.
    assert list(store.items) == [(("library", USER, WORKSPACE), "library_other")]


@pytest.mark.asyncio
async def test_a_keyword_without_kept_results_is_removed(library, allow_permissions):
    store, remove = library
    store.items = {(("library", USER, WORKSPACE), KEY): {"value": {}}}

    assert (await remove()).status_code == 200
    assert store.items == {}


@pytest.mark.asyncio
async def test_another_users_keyword_is_not_found_and_stays(library, allow_permissions):
    store, remove = library
    theirs = {(("library", OTHER, WORKSPACE), KEY): {"value": {}}}
    store.items = dict(theirs)

    response = await remove()

    assert response.status_code == 404
    assert response.json()["message"] == "That keyword isn't in your library."
    assert store.items == theirs


@pytest.mark.asyncio
async def test_a_keyword_already_removed_is_not_found(library, allow_permissions):
    _, remove = library

    response = await remove("library_gone")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_without_the_right_to_read_the_workspaces_content_it_is_refused(library, monkeypatch):
    store, remove = library
    store.items = {(("library", USER, WORKSPACE), KEY): {"value": {}}}
    asked = []

    async def refuse(db, user_id, permissions, workspace_id):
        asked.append(permissions)
        return False

    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", refuse)

    response = await remove()

    assert response.status_code == 403
    assert asked == [["content.read"]]
    assert list(store.items) == [(("library", USER, WORKSPACE), KEY)]
