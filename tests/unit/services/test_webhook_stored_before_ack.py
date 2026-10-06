"""A Lemon Squeezy event is stored before it is acknowledged (F11, revnix/rext-control#336).

Lemon Squeezy sends an event again only when it gets no 2xx, so the route answers
200 only once the event is in webhook_events, an error (503) when it can't be
stored, and processes the stored row in the background.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

from src.api.models.subscription_models.webhooks import WebhookEvent
from src.services.lemonsqueezy_webhook_service import (
    LemonSqueezyWebhookService,
    WebhookProcessingError,
)

PAYLOAD = json.dumps(
    {
        "meta": {"event_name": "subscription_updated", "webhook_id": "wh_1"},
        "data": {"id": "ls_sub_1", "type": "subscriptions", "attributes": {"status": "active"}},
    }
).encode()


@pytest.mark.asyncio
async def test_record_stores_a_new_event_and_reports_a_duplicate():
    svc = LemonSqueezyWebhookService(AsyncMock())
    svc._check_idempotency = AsyncMock(return_value=False)
    svc._log_webhook = AsyncMock()

    recorded = await svc.record_webhook(PAYLOAD)

    assert recorded == {
        "event_id": "wh_1",
        "event_type": "subscription_updated",
        "duplicate": False,
    }
    svc._log_webhook.assert_awaited_once()

    svc._check_idempotency = AsyncMock(return_value=True)
    svc._log_webhook = AsyncMock()
    assert (await svc.record_webhook(PAYLOAD))["duplicate"] is True
    svc._log_webhook.assert_not_called()


def _service_with_stored(event):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = event
    db.execute = AsyncMock(return_value=result)
    return LemonSqueezyWebhookService(db)


@pytest.mark.asyncio
async def test_process_recorded_runs_the_stored_event_once():
    event = WebhookEvent(
        id=uuid4(),
        event_id="wh_1",
        event_name="subscription_updated",
        payload=json.loads(PAYLOAD),
        processed=False,
    )
    svc = _service_with_stored(event)
    svc._route_event = AsyncMock(return_value={"send_email": False})
    svc._mark_processed = AsyncMock()

    result = await svc.process_recorded("wh_1")

    assert result["handler_result"] == {"send_email": False}
    routed_type, routed_data, _ = svc._route_event.await_args.args
    assert routed_type == "subscription_updated"
    assert routed_data["data"]["id"] == "ls_sub_1"
    svc._mark_processed.assert_awaited_once_with(event)

    event.processed = True
    svc._route_event.reset_mock()
    assert (await svc.process_recorded("wh_1"))["message"] == "Nothing to process"
    svc._route_event.assert_not_called()


@pytest.mark.asyncio
async def test_a_failing_handler_marks_the_stored_event_failed():
    event = WebhookEvent(
        id=uuid4(), event_id="wh_2", event_name="subscription_updated", payload={}, processed=False
    )
    svc = _service_with_stored(event)
    svc._route_event = AsyncMock(side_effect=ValueError("boom"))
    svc._mark_failed = AsyncMock()

    with pytest.raises(WebhookProcessingError):
        await svc.process_recorded("wh_2")
    svc._mark_failed.assert_awaited_once()


def _request():
    request = MagicMock()
    request.body = AsyncMock(return_value=PAYLOAD)
    request.headers = {"X-Signature": "sig"}
    request.client.host = "127.0.0.1"
    return request


async def _post(record):
    from src.api.routes.subscriptions import webhook_routes

    tasks = BackgroundTasks()
    with (
        patch.object(webhook_routes, "verify_webhook_signature", return_value=True),
        patch.object(webhook_routes.audit_logger, "log_webhook_received", AsyncMock()),
        patch.object(webhook_routes.LemonSqueezyWebhookService, "record_webhook", record),
    ):
        response = await webhook_routes.handle_lemonsqueezy_webhook(_request(), tasks, None)
    return response, tasks


@pytest.mark.asyncio
async def test_the_route_acknowledges_only_a_stored_event():
    record = AsyncMock(
        return_value={"event_id": "wh_1", "event_type": "subscription_updated", "duplicate": False}
    )

    response, tasks = await _post(record)

    assert response["status"] == "accepted"
    assert [(t.args, t.kwargs) for t in tasks.tasks] == [(("wh_1", "subscription_updated"), {})]


@pytest.mark.asyncio
async def test_an_event_that_can_t_be_stored_is_refused_so_it_comes_again():
    with pytest.raises(HTTPException) as refused:
        await _post(AsyncMock(side_effect=ConnectionError("database down")))

    assert refused.value.status_code == 503


@pytest.mark.asyncio
async def test_a_duplicate_is_acknowledged_without_processing():
    record = AsyncMock(
        return_value={"event_id": "wh_1", "event_type": "subscription_updated", "duplicate": True}
    )

    response, tasks = await _post(record)

    assert response["status"] == "duplicate"
    assert tasks.tasks == []


@pytest.mark.asyncio
async def test_the_losing_insert_of_a_double_delivery_is_a_duplicate():
    svc = LemonSqueezyWebhookService(AsyncMock())
    svc._check_idempotency = AsyncMock(return_value=False)  # both deliveries passed the check
    stored_by_the_other = WebhookEvent(id=uuid4(), event_id="wh_1", event_name="x")
    stored_by_the_other._inserted_here = False
    svc._log_webhook = AsyncMock(return_value=stored_by_the_other)

    assert (await svc.record_webhook(PAYLOAD))["duplicate"] is True


@pytest.mark.asyncio
async def test_a_failing_handler_releases_its_claim_before_marking_the_row():
    event = WebhookEvent(
        id=uuid4(), event_id="wh_3", event_name="subscription_updated", payload={}, processed=False
    )
    svc = _service_with_stored(event)
    order = []
    svc.db.rollback = AsyncMock(side_effect=lambda: order.append("rollback"))
    svc._route_event = AsyncMock(side_effect=ValueError("boom"))
    svc._mark_failed = AsyncMock(side_effect=lambda *_a: order.append("mark_failed"))

    with pytest.raises(WebhookProcessingError):
        await svc.process_recorded("wh_3")
    # _mark_failed writes the row from its own session, so the claim goes first.
    assert order == ["rollback", "mark_failed"]


@pytest.mark.asyncio
async def test_reprocessing_returns_the_handler_s_emails():
    event = WebhookEvent(
        id=uuid4(), event_id="wh_4", event_name="subscription_payment_success", payload={}
    )
    svc = LemonSqueezyWebhookService(AsyncMock())
    svc._route_event = AsyncMock(
        return_value={"send_email": True, "email_type": "payment_succeeded"}
    )

    result = await svc.reprocess_event(event)

    assert result["handler_result"]["email_type"] == "payment_succeeded"


@pytest.mark.asyncio
async def test_a_retried_event_sends_its_emails_after_the_commit():
    from src.services import webhook_monitoring_service as monitoring

    email, notice = AsyncMock(), AsyncMock()
    with (
        patch("src.api.routes.subscriptions.webhook_routes._send_webhook_email", email),
        patch("src.api.routes.subscriptions.webhook_routes._send_webhook_notification", notice),
    ):
        await monitoring._send_post_commit_tasks({"send_email": True, "email_type": "x"})
        await monitoring._send_post_commit_tasks({"send_email": False})
        await monitoring._send_post_commit_tasks(None)

    email.assert_awaited_once()
    notice.assert_awaited_once()
