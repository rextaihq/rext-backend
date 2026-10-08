"""Money events for product analytics (rext-control task 712, step C).

One anonymous event per Lemon Squeezy webhook that means money moved or a plan
started or ended, sent after the webhook's work is committed. Never who.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services import money_events
from src.services.money_events import money_event, record_money_event, send_money_event


def _subscription(**attributes):
    return {
        "meta": {"event_name": "subscription_created", "custom_data": {"user_id": "user-1"}},
        "data": {
            "id": "ls_sub_1",
            "type": "subscriptions",
            "attributes": {
                "variant_name": "Growth",
                "product_name": "Rext",
                "status": "active",
                "user_email": "mary@example.com",
                "user_name": "Mary",
                "customer_id": 42,
                "order_id": 7,
                **attributes,
            },
        },
    }


def _invoice(**attributes):
    return {
        "meta": {"event_name": "subscription_payment_success"},
        "data": {
            "id": "ls_inv_1",
            "type": "subscription-invoices",
            "attributes": {
                "billing_reason": "renewal",
                "total": 4900,
                "currency": "USD",
                "status": "paid",
                "user_email": "mary@example.com",
                "subscription_id": 9,
                **attributes,
            },
        },
    }


def test_a_started_subscription_says_which_plan_and_never_who():
    event = money_event("subscription_created", _subscription())

    assert event == {
        "event": "subscription_started",
        "properties": {"plan": "Growth", "product": "Rext", "status": "active"},
    }
    sent = json.dumps(event)
    for private in ("mary", "user-1", "ls_sub_1", "42"):
        assert private not in sent


def test_a_renewal_carries_the_amount_in_the_currency_s_unit():
    event = money_event("subscription_payment_success", _invoice())

    assert event["event"] == "subscription_renewed"
    assert event["properties"] == {
        "status": "paid",
        "currency": "USD",
        "billing_reason": "renewal",
        "amount": 49.0,
    }


@pytest.mark.parametrize("reason", ["initial", "updated", None])
def test_a_first_payment_or_a_plan_change_s_charge_is_not_a_renewal(reason):
    assert money_event("subscription_payment_success", _invoice(billing_reason=reason)) is None


@pytest.mark.parametrize(
    ("theirs", "ours"),
    [
        ("subscription_cancelled", "subscription_cancelled"),
        ("subscription_expired", "subscription_expired"),
        ("subscription_payment_failed", "subscription_payment_failed"),
        ("order_refunded", "subscription_refunded"),
        ("subscription_payment_refunded", "subscription_payment_refunded"),
    ],
)
def test_the_other_money_events_have_a_name_of_ours(theirs, ours):
    assert money_event(theirs, _subscription())["event"] == ours


def test_a_refund_gives_the_running_total_under_a_name_that_says_so():
    # Lemon Squeezy's refunded_amount is what has come back so far: after 10 and then
    # another 9, the second webhook says 19. It is never sent as this refund's amount.
    payload = {
        "meta": {},
        "data": {"attributes": {"total": 4900, "refunded_amount": 1900, "currency": "EUR"}},
    }

    assert money_event("order_refunded", payload)["properties"] == {
        "currency": "EUR",
        "amount": 49.0,
        "refunded_total": 19.0,
        "full_refund": False,
    }


def test_a_refund_of_everything_says_so():
    payload = {"meta": {}, "data": {"attributes": {"total": 4900, "refunded_amount": 4900}}}

    properties = money_event("order_refunded", payload)["properties"]

    assert properties["full_refund"] is True
    assert "refunded_amount" not in properties


def test_a_refunded_renewal_is_counted_under_its_own_name():
    event = money_event("subscription_payment_refunded", _invoice(status="refunded"))

    assert event["event"] == "subscription_payment_refunded"
    assert event["properties"]["billing_reason"] == "renewal"


@pytest.mark.parametrize("event_type", ["subscription_updated", "order_created", "unknown"])
def test_an_event_that_moves_no_money_sends_nothing(event_type):
    assert money_event(event_type, _subscription()) is None


def test_a_sandbox_purchase_is_never_counted():
    in_meta = _subscription()
    in_meta["meta"]["test_mode"] = True

    assert money_event("subscription_created", in_meta) is None
    assert money_event("subscription_created", _subscription(test_mode=True)) is None


def _client(requests, status=200):
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"status": 1})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_nothing_is_sent_without_the_project_s_key(monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_KEY", raising=False)
    requests = []

    async with _client(requests) as client:
        sent = await send_money_event(
            "evt_1", "subscription_created", _subscription(), client=client
        )

    assert sent is False
    assert requests == []


async def test_the_event_goes_to_posthog_with_no_person_and_an_id_of_its_own(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    requests = []
    at = datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc)

    async with _client(requests) as client:
        first = await send_money_event(
            "evt_1", "subscription_created", _subscription(), at, client=client
        )
        again = await send_money_event(
            "evt_1", "subscription_created", _subscription(), at, client=client
        )

    assert first is True and again is True
    assert str(requests[0].url) == "https://eu.i.posthog.com/i/v0/e/"
    body = json.loads(requests[0].content)
    assert body["api_key"] == "phc_test"
    assert body["event"] == "subscription_started"
    assert body["properties"]["$process_person_profile"] is False
    assert body["properties"]["source"] == "backend"
    assert body["properties"]["surface"] == "app"
    assert body["timestamp"] == "2026-10-08T05:00:00+00:00"
    # No identity: the id is made from the webhook's, and is the event's own.
    assert body["distinct_id"] == body["uuid"]
    for private in ("mary", "user-1", "ls_sub_1"):
        assert private not in requests[0].content.decode()
    # A retry is the same event again, not a second one.
    assert json.loads(requests[1].content)["uuid"] == body["uuid"]


async def test_a_refusal_or_a_failure_never_reaches_the_webhook(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    requests = []

    async with _client(requests, status=503) as client:
        assert (
            await send_money_event("evt_1", "subscription_created", _subscription(), client=client)
            is False
        )

    def broken(request):
        raise httpx.ConnectError("no route", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(broken)) as client:
        assert (
            await send_money_event("evt_1", "subscription_created", _subscription(), client=client)
            is False
        )


async def test_recording_reads_the_stored_webhook_and_sends_its_event(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    row = MagicMock(
        event_name="subscription_created",
        payload=_subscription(),
        created_at=datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc),
    )
    db = AsyncMock()
    db.execute.return_value = MagicMock(first=MagicMock(return_value=row))

    with patch.object(money_events, "send_money_event", new=AsyncMock(return_value=True)) as send:
        assert await record_money_event(db, "evt_1") is True

    send.assert_awaited_once_with("evt_1", "subscription_created", row.payload, row.created_at)


async def test_recording_reads_nothing_when_analytics_is_not_configured(monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_KEY", raising=False)
    db = AsyncMock()

    assert await record_money_event(db, "evt_1") is False
    db.execute.assert_not_called()


async def test_recording_survives_a_database_that_fails(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("connection lost")

    assert await record_money_event(db, "evt_1") is False
    assert await record_money_event(db, None) is False
