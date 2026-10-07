"""
Focused tests for the webhook monitoring retry / reprocessing contract.

Covers:
- The full handler registry is shared between the live receiver and the admin
  retry flow (Task 2 - retries actually reprocess).
- ``_serialize_event`` reports a status string consistent with the list
  endpoints (Task 6 - response contract).
- Identifier contract: ``retry_webhook`` locates the event by its database id
  (``webhook_events.id``), not the external LemonSqueezy ``event_id`` (Task 3).
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService
from src.services.webhook_handlers import register_default_handlers
from src.services.webhook_monitoring_service import WebhookMonitoringService

EXPECTED_HANDLERS = {
    "subscription_created",
    "subscription_updated",
    "subscription_cancelled",
    "subscription_resumed",
    "subscription_expired",
    "subscription_paused",
    "subscription_payment_success",
    "subscription_payment_failed",
    "subscription_payment_recovered",
    "order_created",
    "order_refunded",
}


def test_register_default_handlers_covers_all_event_types():
    svc = LemonSqueezyWebhookService(MagicMock())
    register_default_handlers(svc)
    assert set(svc._handlers) == EXPECTED_HANDLERS


def _fake_event(**overrides):
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        event_id="evt_external_123",
        event_name="subscription_created",
        processed=False,
        processed_at=None,
        error_message=None,
        retry_count=0,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.parametrize(
    "event_kwargs,expected_status",
    [
        (dict(processed=True, error_message=None), "processed"),
        (dict(processed=False, error_message="boom"), "failed"),
        (dict(processed=False, error_message=None), "pending"),
    ],
)
def test_serialize_event_status(event_kwargs, expected_status):
    service = WebhookMonitoringService(MagicMock())
    serialized = service._serialize_event(_fake_event(**event_kwargs))
    assert serialized["status"] == expected_status
    # id is the DB identifier, event_id is the external LemonSqueezy id.
    assert serialized["id"] == "11111111-1111-1111-1111-111111111111"
    assert serialized["event_id"] == "evt_external_123"


@pytest.mark.asyncio
async def test_retry_webhook_looks_up_by_database_id():
    """retry_webhook must query WebhookEvent by its ``id`` column."""
    from uuid import UUID

    service = WebhookMonitoringService(MagicMock())

    captured = {}

    async def fake_execute(stmt):
        # Render the compiled WHERE clause and make sure it targets id, not event_id.
        captured["sql"] = str(stmt)
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        return result

    service.db = MagicMock()
    service.db.execute = AsyncMock(side_effect=fake_execute)

    webhook_id = UUID("11111111-1111-1111-1111-111111111111")
    out = await service.retry_webhook(webhook_id)

    assert out["success"] is False
    assert "not found" in out["message"].lower()
    where_clause = captured["sql"].split("WHERE", 1)[1]
    assert "webhook_events.id" in where_clause
    assert "webhook_events.event_id" not in where_clause


def _session_returning(row):
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)
    db.commit, db.rollback, db.close = AsyncMock(), AsyncMock(), AsyncMock()
    return db


@pytest.mark.parametrize(
    "claimed_row",
    [None, _fake_event(processed=True, error_message=None)],
    ids=["held by another run", "processed by the time it is held"],
)
@pytest.mark.asyncio
async def test_a_retry_runs_nothing_when_another_run_has_the_event(monkeypatch, claimed_row):
    """The scheduled and an admin retry can overlap: one claims the row, the other skips."""
    import src.services.webhook_monitoring_service as monitoring

    failed = _fake_event(processed=False, error_message="boom")
    service = WebhookMonitoringService(_session_returning(failed))
    processing_db = _session_returning(claimed_row)
    monkeypatch.setattr(monitoring, "AsyncSessionLocal", lambda: processing_db)
    reprocess = AsyncMock()
    monkeypatch.setattr(LemonSqueezyWebhookService, "reprocess_event", reprocess)

    out = await service.retry_webhook(failed.id)

    assert out["success"] is False
    assert "another run" in out["message"]
    reprocess.assert_not_called()
    claim = processing_db.execute.await_args.args[0]
    assert claim._for_update_arg is not None and claim._for_update_arg.skip_locked


@pytest.mark.asyncio
async def test_a_claimed_retry_is_marked_done_in_the_handlers_transaction(monkeypatch):
    import src.services.webhook_monitoring_service as monitoring

    failed = _fake_event(processed=False, error_message="boom")
    service = WebhookMonitoringService(_session_returning(failed))
    processing_db = _session_returning(_fake_event(processed=False, error_message="boom"))
    status_db = MagicMock()
    status_db.__aenter__.return_value.get = AsyncMock(return_value=_fake_event())
    status_db.__aenter__.return_value.commit = AsyncMock()
    sessions = iter([processing_db, status_db])
    monkeypatch.setattr(monitoring, "AsyncSessionLocal", lambda: next(sessions))
    order = []
    monkeypatch.setattr(
        LemonSqueezyWebhookService,
        "reprocess_event",
        AsyncMock(side_effect=lambda **_: order.append("handler") or {"handler_result": None}),
    )
    monkeypatch.setattr(
        LemonSqueezyWebhookService,
        "_mark_processed",
        AsyncMock(side_effect=lambda *_: order.append("marked")),
    )
    processing_db.commit = AsyncMock(side_effect=lambda: order.append("commit"))
    monkeypatch.setattr(monitoring, "_send_post_commit_tasks", AsyncMock())

    out = await service.retry_webhook(failed.id)

    assert out["success"] is True
    assert order == ["handler", "marked", "commit"]
