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
from src.services.money_events import (
    _held_by,
    _plan_queries,
    money_event,
    record_money_event,
    send_money_event,
    send_server_event,
)


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
        "properties": {"product": "Rext", "variant": "Growth", "status": "active"},
    }
    sent = json.dumps(event)
    for private in ("mary", "user-1", "ls_sub_1", "42"):
        assert private not in sent


def test_a_paid_invoice_carries_the_amount_in_the_currency_s_unit():
    event = money_event("subscription_payment_success", _invoice())

    assert event["event"] == "subscription_payment_succeeded"
    assert event["properties"] == {
        "status": "paid",
        "currency": "USD",
        "billing_reason": "renewal",
        "amount": 49.0,
    }


@pytest.mark.parametrize("reason", ["initial", "renewal", "updated"])
def test_every_paid_invoice_is_counted_with_what_it_was_for(reason):
    # A first payment and a plan change's charge move money as a renewal does.
    event = money_event("subscription_payment_success", _invoice(billing_reason=reason))

    assert event["event"] == "subscription_payment_succeeded"
    assert event["properties"]["billing_reason"] == reason
    assert event["properties"]["amount"] == 49.0


@pytest.mark.parametrize("currency", ["USD", "EUR", "JPY", "KWD", None])
def test_an_amount_is_read_as_the_books_read_it_with_the_dollar_figure_beside_it(currency):
    # Hundredths whatever the currency, as the orders and the refunds are kept: the event's
    # figure is the books' figure. What a chart adds up across currencies is amount_usd.
    event = money_event(
        "subscription_payment_success",
        _invoice(currency=currency, total=4999, total_usd=4100, refunded_amount=1000),
    )

    assert event["properties"]["amount"] == 49.99
    assert event["properties"]["refunded_total"] == 10.0
    assert event["properties"]["amount_usd"] == 41.0


def test_an_amount_that_is_not_a_number_is_left_out():
    for total in (True, "abc", None):
        assert (
            "amount"
            not in money_event("subscription_payment_success", _invoice(total=total))["properties"]
        )


def test_the_plan_is_the_backend_s_own_name_for_it():
    # An invoice names no plan: it comes from the subscription the backend holds.
    held = {"plan": "growth", "billing_period": "yearly"}

    properties = money_event("subscription_payment_success", _invoice(), held)["properties"]

    assert properties["plan"] == "growth"
    assert properties["billing_period"] == "yearly"
    assert "plan" not in money_event("subscription_payment_success", _invoice())["properties"]
    # Only words: nothing else that a lookup might hand over is passed on.
    odd = money_event("subscription_payment_success", _invoice(), {"plan": 7, "user_id": "u"})
    assert "plan" not in odd["properties"] and "user_id" not in odd["properties"]


def test_a_refunded_order_names_its_product_from_its_first_item():
    payload = {
        "meta": {},
        "data": {
            "id": "501",
            "attributes": {
                "total": 4900,
                "refunded_amount": 4900,
                "currency": "USD",
                "user_email": "mary@example.com",
                "first_order_item": {
                    "product_name": "Rext",
                    "variant_name": "Growth",
                    "price": 4900,
                    "order_id": 501,
                },
            },
        },
    }

    event = money_event("order_refunded", payload)

    assert event["properties"]["product"] == "Rext"
    assert event["properties"]["variant"] == "Growth"
    assert "mary" not in json.dumps(event) and "order_id" not in event["properties"]


@pytest.mark.parametrize(
    ("event_type", "payload", "found"),
    [
        ("subscription_created", {"data": {"id": "ls_sub_1"}}, ("subscription", "ls_sub_1")),
        (
            "subscription_payment_success",
            {"data": {"id": "ls_inv_1", "attributes": {"subscription_id": 9}}},
            ("subscription", "9"),
        ),
        (
            "subscription_payment_refunded",
            {"data": {"id": "ls_inv_1", "attributes": {"subscription_id": 9}}},
            ("subscription", "9"),
        ),
        ("order_refunded", {"data": {"id": 501}}, ("order", "501")),
        ("subscription_payment_success", {"data": {"id": "ls_inv_1", "attributes": {}}}, None),
        ("license_key_created", {"data": {"id": "1"}}, None),
    ],
)
def test_the_subscription_a_webhook_is_about_is_found_by_what_it_names(event_type, payload, found):
    assert _held_by(event_type, payload) == found


def test_a_plan_change_s_invoice_names_no_plan():
    # Its webhook can arrive before the one that moves the subscription to the new plan, so
    # what the backend holds may be the plan being left: better none than the wrong one.
    changed = {"data": {"attributes": {"subscription_id": 9, "billing_reason": "updated"}}}
    renewed = {"data": {"attributes": {"subscription_id": 9, "billing_reason": "renewal"}}}

    assert _held_by("subscription_payment_success", changed) is None
    assert _held_by("subscription_payment_success", renewed) == ("subscription", "9")


def test_an_order_s_plan_is_looked_for_in_the_orders_table_first():
    by_order = [str(query) for query in _plan_queries("order", "501")]
    by_subscription = [str(query) for query in _plan_queries("subscription", "9")]

    assert len(by_order) == 2 and len(by_subscription) == 1
    assert "JOIN orders" in by_order[0] and "orders.lemonsqueezy_order_id" in by_order[0]
    assert "orders" not in by_order[1]
    assert "user_subscriptions.lemonsqueezy_order_id" in by_order[1]
    assert "user_subscriptions.lemonsqueezy_subscription_id" in by_subscription[0]


@pytest.mark.parametrize(
    ("theirs", "ours"),
    [
        ("subscription_payment_success", "subscription_payment_succeeded"),
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


def test_a_refund_without_an_amount_still_says_when_all_of_it_came_back():
    payload = {"meta": {}, "data": {"attributes": {"refunded": True, "status": "refunded"}}}

    assert money_event("order_refunded", payload)["properties"] == {
        "status": "refunded",
        "full_refund": True,
    }
    partial = {"meta": {}, "data": {"attributes": {"refunded": True, "status": "partial_refund"}}}
    assert "full_refund" not in money_event("order_refunded", partial)["properties"]


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


AT = datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc)


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
    monkeypatch.setenv("ENVIRONMENT", "Production")
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
    assert body["properties"]["source"] == "server"
    assert body["properties"]["surface"] == "app"
    assert body["properties"]["environment"] == "production"
    assert body["timestamp"] == "2026-10-08T05:00:00+00:00"
    # No identity: the id is made from the webhook's, and is the event's own.
    assert body["distinct_id"] == body["uuid"]
    for private in ("mary", "user-1", "ls_sub_1"):
        assert private not in requests[0].content.decode()
    # A retry is the same event again, not a second one.
    assert json.loads(requests[1].content)["uuid"] == body["uuid"]


async def test_a_server_event_carries_the_person_only_when_one_is_given(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    requests = []

    async with _client(requests) as client:
        await send_server_event(
            "workspace_created",
            {"first_workspace": True},
            key="ws-1",
            occurred_at=AT,
            client=client,
        )
        await send_server_event(
            "workspace_created",
            {"first_workspace": True},
            key="ws-1",
            occurred_at=AT,
            person_id="user-1",
            client=client,
        )

    anonymous, known = (json.loads(request.content) for request in requests)
    assert anonymous["properties"]["$process_person_profile"] is False
    assert anonymous["distinct_id"] == anonymous["uuid"]
    assert known["distinct_id"] == "user-1"
    assert "$process_person_profile" not in known["properties"]
    # The same thing that happened is the same event either way.
    assert known["uuid"] == anonymous["uuid"]
    for body in (anonymous, known):
        assert body["event"] == "workspace_created"
        # Sent again, it is the same event only with the same time.
        assert body["timestamp"] == "2026-10-08T05:00:00+00:00"
        assert body["properties"] == {
            **body["properties"],
            "first_workspace": True,
            "surface": "app",
            "source": "server",
            "environment": "staging",
        }


async def test_two_kinds_of_event_about_one_thing_are_two_events(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    requests = []

    async with _client(requests) as client:
        await send_server_event("credits_spent", {}, key="row-1", occurred_at=AT, client=client)
        await send_server_event("credits_low", {}, key="row-1", occurred_at=AT, client=client)

    first, second = (json.loads(request.content)["uuid"] for request in requests)
    assert first != second


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


async def test_an_answer_that_says_the_project_is_over_quota_is_not_a_success(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")

    def over_quota(request):
        return httpx.Response(200, json={"status": 1, "quota_limited": ["events"]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(over_quota)) as client:
        assert (
            await send_server_event("credits_spent", {}, key="row-1", occurred_at=AT, client=client)
            is False
        )

    def not_json(request):
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(not_json)) as client:
        assert (
            await send_server_event("credits_spent", {}, key="row-1", occurred_at=AT, client=client)
            is True
        )


async def test_the_sender_asks_for_the_time_and_an_event_without_one_carries_none(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    requests = []

    async with _client(requests) as client:
        with pytest.raises(TypeError):
            await send_server_event("credits_spent", {}, key="row-1", client=client)
        assert (
            await send_server_event(
                "credits_spent", {}, key="row-1", occurred_at=None, client=client
            )
            is True
        )

    assert len(requests) == 1
    assert "timestamp" not in json.loads(requests[0].content)


def _rows(*rows):
    """A session whose reads answer with these rows, one read each."""
    db = AsyncMock()
    db.execute.side_effect = [MagicMock(first=MagicMock(return_value=row)) for row in rows]
    return db


async def test_recording_reads_the_stored_webhook_and_sends_its_event(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    row = MagicMock(event_name="subscription_created", payload=_subscription(), created_at=AT)
    # The subscription the backend holds: its plan's name and its period, as the model has it.
    plan = MagicMock(billing_period=MagicMock(value="yearly"))
    plan.name = "growth"
    db = _rows(row, plan)

    with patch.object(money_events, "send_money_event", new=AsyncMock(return_value=True)) as send:
        assert await record_money_event(db, "evt_1") is True

    send.assert_awaited_once_with(
        "evt_1",
        "subscription_created",
        row.payload,
        row.created_at,
        held={"plan": "growth", "billing_period": "yearly"},
    )


async def test_recording_sends_without_a_plan_when_none_is_held_or_the_read_fails(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    row = MagicMock(event_name="subscription_payment_success", payload=_invoice(), created_at=AT)

    with patch.object(money_events, "send_money_event", new=AsyncMock(return_value=True)) as send:
        assert await record_money_event(_rows(row, None), "evt_1") is True
        failing = _rows(row)
        failing.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=row)),
            RuntimeError("connection lost"),
        ]
        assert await record_money_event(failing, "evt_2") is True

    assert [call.kwargs for call in send.await_args_list] == [{"held": None}, {"held": None}]
    # The caller goes on using its session: a failed read is rolled back, not left broken.
    failing.rollback.assert_awaited_once()


async def test_recording_finds_a_refunded_order_s_plan_by_the_second_read(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    payload = {"meta": {}, "data": {"id": 501, "attributes": {"total": 4900}}}
    row = MagicMock(event_name="order_refunded", payload=payload, created_at=AT)
    plan = MagicMock(billing_period="monthly")
    plan.name = "starter"
    # The orders table has no row for it; the subscription's own copy of the order's id does.
    db = _rows(row, None, plan)

    with patch.object(money_events, "send_money_event", new=AsyncMock(return_value=True)) as send:
        assert await record_money_event(db, "evt_1") is True

    assert db.execute.await_count == 3
    assert send.await_args.kwargs == {"held": {"plan": "starter", "billing_period": "monthly"}}


async def test_recording_reads_no_plan_for_a_webhook_with_no_event(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    row = MagicMock(event_name="subscription_updated", payload=_subscription(), created_at=AT)
    db = _rows(row)

    assert await record_money_event(db, "evt_1") is False
    assert db.execute.await_count == 1


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
