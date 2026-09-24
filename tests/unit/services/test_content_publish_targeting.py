"""Which WordPress post a republish edits, and which author it credits.

ContentService resolves both before any HTTP call, so these exercise the
resolution alone with a stubbed session rather than a live database.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.services.content_service import (
    WORDPRESS_AUTHORS_KEY,
    ContentService,
    remember_wordpress_author,
    wordpress_author_kwargs,
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _StubDB:
    """Returns a queued result per execute() call, in order."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, _statement):
        self.calls += 1
        return _Result(self._results.pop(0) if self._results else [])


def _site(site_url, integration_type="wordpress"):
    return SimpleNamespace(
        id=uuid4(), site_url=site_url, integration_type=integration_type, config_json=None
    )


def _content(**kwargs):
    defaults = {
        "id": uuid4(),
        "persona_id": None,
        "wordpress_post_id": None,
        "wordpress_url": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_existing_post_comes_from_the_publishing_result_for_that_site():
    site = _site("https://blog.example.com")
    content = _content()
    publishing_result = SimpleNamespace(site_id=site.id, wp_post_id=612)
    service = ContentService(_StubDB([publishing_result]))

    existing = await service.existing_wordpress_post_ids(content, [site])

    assert existing == {site.id: 612}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_legacy_content_falls_back_to_its_recorded_post_on_the_matching_site():
    """Rows published before per-site results existed still republish in place."""
    site = _site("https://blog.example.com")
    content = _content(wordpress_post_id=88, wordpress_url="https://blog.example.com/?p=88")
    service = ContentService(_StubDB([]))

    existing = await service.existing_wordpress_post_ids(content, [site])

    assert existing == {site.id: 88}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_post_on_another_site_is_never_reused():
    """Publishing to a second site must create a post there, not edit the first."""
    other_site = _site("https://shop.example.net")
    content = _content(wordpress_post_id=88, wordpress_url="https://blog.example.com/?p=88")
    service = ContentService(_StubDB([]))

    existing = await service.existing_wordpress_post_ids(content, [other_site])

    assert existing == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shopify_sites_are_not_given_a_wordpress_post_id():
    shopify = _site("https://store.example.com", integration_type="shopify")
    content = _content(wordpress_post_id=88, wordpress_url="https://store.example.com/?p=88")
    service = ContentService(_StubDB([]))

    assert await service.existing_wordpress_post_ids(content, [shopify]) == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publish_context_carries_the_outline_author_persona():
    site = _site("https://blog.example.com")
    persona_id = uuid4()
    content = _content(persona_id=persona_id)
    persona = SimpleNamespace(
        id=persona_id,
        name="sara",
        full_name="Sara Ortiz",
        email="sara@example.com",
    )
    service = ContentService(_StubDB([persona], []))

    context = await service.wordpress_publish_context(content, site)

    assert context["author_name"] == "Sara Ortiz"
    assert context["author_email"] == "sara@example.com"
    assert context["post_id"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_content_written_with_no_persona_has_no_author_to_pass_on():
    site = _site("https://blog.example.com")
    service = ContentService(_StubDB([]))

    context = await service.wordpress_publish_context(_content(), site)

    assert context["author_name"] is None
    assert context["author_email"] is None


def _persona(**kwargs):
    defaults = {
        "id": uuid4(),
        "name": "sara",
        "full_name": "Sara Ortiz",
        "email": "sara@example.com",
        "bio": "Writes about gardens.",
        "avatar_url": "https://cdn.example.com/sara.png",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.unit
def test_author_kwargs_carry_the_whole_persona_and_the_user_it_was_credited_to():
    persona = _persona()
    config = {WORDPRESS_AUTHORS_KEY: {str(persona.id): 7}}

    kwargs = wordpress_author_kwargs(persona, config)

    assert kwargs == {
        "author_name": "Sara Ortiz",
        "author_email": "sara@example.com",
        "author_bio": "Writes about gardens.",
        "author_avatar_url": "https://cdn.example.com/sara.png",
        "author_persona_id": str(persona.id),
        "author_user_id": 7,
    }


@pytest.mark.unit
def test_author_kwargs_drop_an_avatar_wordpress_cannot_fetch():
    kwargs = wordpress_author_kwargs(_persona(avatar_url="personas/sara.png"), None)

    assert kwargs["author_avatar_url"] is None
    assert kwargs["author_user_id"] is None


@pytest.mark.unit
def test_no_persona_means_no_author_arguments():
    assert wordpress_author_kwargs(None, {}) == {}


@pytest.mark.unit
def test_a_confirmed_byline_is_remembered_on_the_site():
    site = SimpleNamespace(config_json={"other": True})
    persona_id = uuid4()

    remember_wordpress_author(site, persona_id, {"author_id": 15, "author_applied": True})

    assert site.config_json == {"other": True, WORDPRESS_AUTHORS_KEY: {str(persona_id): 15}}


@pytest.mark.unit
def test_a_byline_wordpress_refused_is_not_remembered():
    site = SimpleNamespace(config_json=None)

    remember_wordpress_author(site, uuid4(), {"author_id": 15, "author_applied": False})

    assert site.config_json is None
