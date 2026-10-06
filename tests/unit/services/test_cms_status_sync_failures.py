"""A status check that fails is a failed sync, not a successful sync to "unknown" (G29).

The WordPress and Shopify status calls report a timeout, a 5xx or a refused address as
``success: False`` rather than raising. CMSStatusService used to ignore that, map the status to
UNKNOWN, clear ``sync_error`` and count the record as synced. These run the service against a
stubbed session and stubbed CMS clients, so no database or network is involved.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.services.cms_status_service as cms_status
from src.api.models.content_models.publishing_result import PublishingStatus
from src.services.cms_status_service import CMSStatusService


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _StubDB:
    """get() reads the given records by id; execute() returns a queued result per call, in order."""

    def __init__(self, records=(), *results):
        self._by_id = {r.id: r for r in records}
        self._results = list(results)

    async def get(self, _model, key):
        return self._by_id.get(key)

    async def execute(self, _statement):
        return _Result(self._results.pop(0) if self._results else [])

    async def flush(self):
        return None


def _client(answer):
    """A stand-in for WordPressPublisher or ShopifyConnector whose status call gives `answer`."""

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def _status(self, *_args, **_kwargs):
            if isinstance(answer, Exception):
                raise answer
            return answer

        get_post_status = _status
        get_article_status = _status

    return _Client


def _site(integration_type="wordpress", **kwargs):
    defaults = {
        "id": uuid4(),
        "integration_type": integration_type,
        "is_active": True,
        "site_url": "https://example.com",
        "username": "editor",
        "app_password": "not-a-secret",
        "api_key": "token" if integration_type == "shopify" else None,
        "api_endpoint": None,
        "config_json": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _record(site, status=PublishingStatus.PUBLISHED, **kwargs):
    defaults = {
        "id": uuid4(),
        "site_id": site.id,
        "content_id": uuid4(),
        "status": status,
        "wp_post_id": 42 if site.integration_type == "wordpress" else None,
        "shopify_article_id": 7 if site.integration_type == "shopify" else None,
        "shopify_blog_id": 3 if site.integration_type == "shopify" else None,
        "sync_error": "an earlier error",
        "last_synced_at": None,
        "external_url": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


FAILED = {"status": "unknown", "success": False, "error": "timed out"}


@pytest.mark.parametrize("integration_type", ["wordpress", "shopify"])
async def test_a_failed_status_check_keeps_the_status_and_records_the_error(
    monkeypatch, integration_type
):
    monkeypatch.setattr(cms_status, "WordPressPublisher", _client(FAILED))
    monkeypatch.setattr(cms_status, "ShopifyConnector", _client(FAILED))
    site = _site(integration_type)
    record = _record(site)

    await CMSStatusService(_StubDB([record, site])).sync_content_status(record.id)

    assert record.status == PublishingStatus.PUBLISHED
    assert "status check failed: timed out" in record.sync_error
    assert record.last_synced_at is None


@pytest.mark.parametrize("integration_type", ["wordpress", "shopify"])
async def test_a_status_call_that_raises_keeps_the_status(monkeypatch, integration_type):
    monkeypatch.setattr(cms_status, "WordPressPublisher", _client(RuntimeError("refused")))
    monkeypatch.setattr(cms_status, "ShopifyConnector", _client(RuntimeError("refused")))
    site = _site(integration_type)
    record = _record(site, status=PublishingStatus.SCHEDULED)

    await CMSStatusService(_StubDB([record, site])).sync_content_status(record.id)

    assert record.status == PublishingStatus.SCHEDULED
    assert record.sync_error == "refused"
    assert record.last_synced_at is None


@pytest.mark.parametrize(
    ("integration_type", "answer", "expected"),
    [
        ("wordpress", {"status": "draft", "success": True}, PublishingStatus.DRAFT),
        ("wordpress", {"status": "deleted", "success": True}, PublishingStatus.DELETED),
        ("shopify", {"status": "draft", "success": True}, PublishingStatus.DRAFT),
    ],
)
async def test_a_successful_status_check_updates_the_status_and_clears_the_error(
    monkeypatch, integration_type, answer, expected
):
    monkeypatch.setattr(cms_status, "WordPressPublisher", _client(answer))
    monkeypatch.setattr(cms_status, "ShopifyConnector", _client(answer))
    site = _site(integration_type)
    record = _record(site)

    await CMSStatusService(_StubDB([record, site])).sync_content_status(record.id)

    assert record.status == expected
    assert record.sync_error is None
    assert isinstance(record.last_synced_at, datetime)
    assert record.last_synced_at.tzinfo == timezone.utc


async def test_a_record_without_a_post_id_keeps_its_error():
    site = _site("wordpress")
    record = _record(site, wp_post_id=None, sync_error=None)

    await CMSStatusService(_StubDB([record, site])).sync_content_status(record.id)

    assert record.sync_error == "No WordPress post ID recorded; publish may have failed."
    assert record.status == PublishingStatus.PUBLISHED


async def test_bulk_sync_counts_a_failed_check_as_failed_and_bridge_mode_as_skipped(monkeypatch):
    ok = _site("wordpress")
    down = _site("wordpress", site_url="https://down.example.com")
    bridge = _site("shopify", api_key=None)

    def wordpress_for(site_url, **_kwargs):
        answer = FAILED if site_url == down.site_url else {"status": "draft", "success": True}
        return _client(answer)()

    monkeypatch.setattr(cms_status, "WordPressPublisher", wordpress_for)
    synced_record = _record(ok)
    failed_record = _record(down)
    missing_id_record = _record(ok, wp_post_id=None)
    bridge_record = _record(bridge)
    records = [synced_record, failed_record, missing_id_record, bridge_record]
    contents = [SimpleNamespace(id=r.content_id, status="published") for r in records]
    db = _StubDB((), records, [ok, down, bridge], contents)

    counts = await CMSStatusService(db).bulk_sync_workspace(uuid4())

    assert counts == {"synced": 1, "failed": 2, "skipped": 1}
    assert synced_record.status == PublishingStatus.DRAFT
    assert synced_record.sync_error is None
    assert failed_record.status == PublishingStatus.PUBLISHED
    assert "status check failed: timed out" in failed_record.sync_error
    assert missing_id_record.sync_error.startswith("No WordPress post ID")
    assert bridge_record.status == PublishingStatus.PUBLISHED
    assert bridge_record.sync_error.startswith("Bridge-mode Shopify")
    # Only the record that was really checked moves its article's status.
    by_content = {c.id: c.status for c in contents}
    assert by_content[synced_record.content_id] == "draft"
    assert by_content[failed_record.content_id] == "published"
