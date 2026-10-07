"""Which WordPress post a republish edits, and which author it credits.

ContentService resolves both before any HTTP call, so these exercise the
resolution alone with a stubbed session rather than a live database.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.services.content_service import ContentService


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
    return SimpleNamespace(id=uuid4(), site_url=site_url, integration_type=integration_type)


def _content(**kwargs):
    defaults = {
        "id": uuid4(),
        "workspace_id": uuid4(),
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
