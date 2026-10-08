"""What a customer paid for a plan change is named on the admin's refund rows (F22, rext-control#804).

Lemon Squeezy charges a plan change as a subscription invoice, which the app's refund of the order
doesn't give back. Found in the launch-offer rehearsal: bought Growth ($89.00), upgraded to Pro
($99.96 charged), refunded in full: $89.00 came back. Until the refund covers the invoice, the
person refunding is told it exists.

The reading is tested on stored events as Lemon Squeezy sends them; the queries on the test
PostgreSQL, in a transaction that is rolled back.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.models.subscription_models.orders import Order
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.users import Users
from src.api.routes.subscriptions.admin import refund_routes
from src.api.schema.response.refund_responses import RefundableOrderRow, RefundRequestRow
from src.services.plan_change_charges import (
    PAID,
    REFUNDED,
    PlanChangeCharge,
    charges_from_events,
    in_its_period,
    plan_change_charges,
    plan_change_charges_for_orders,
)
from tests.conftest import TEST_DATABASE_URL

UPGRADED_AT = datetime(2026, 10, 8, 3, 42, 15, tzinfo=timezone.utc)


def _invoice(
    subscription_id,
    *,
    invoice_id="inv-1",
    reason="updated",
    total=9996,
    at=UPGRADED_AT,
    **attributes,
):
    """A subscription invoice's event body, as Lemon Squeezy sends and the webhook route stores it."""
    return {
        "meta": {"event_name": "subscription_payment_success"},
        "data": {
            "type": "subscription-invoices",
            "id": invoice_id,
            "attributes": {
                "subscription_id": subscription_id,
                "billing_reason": reason,
                "status": "paid",
                "currency": "USD",
                "total": total,
                "created_at": at.isoformat().replace("+00:00", "Z"),
                **attributes,
            },
        },
    }


def test_a_paid_plan_change_is_a_charge_with_its_amount_and_day():
    charges = charges_from_events([(PAID, _invoice(2590065))])

    assert charges == {
        "2590065": [
            PlanChangeCharge(
                invoice_id="inv-1",
                amount=9996,
                refunded_amount=0,
                currency="USD",
                paid_at=charges["2590065"][0].paid_at,
            )
        ]
    }
    (charge,) = charges["2590065"]
    assert charge.outstanding_amount == 9996
    assert charge.paid_at == UPGRADED_AT  # with its zone, so the dashboard shows the right day


@pytest.mark.parametrize("reason", ["initial", "renewal", None])
def test_the_first_payment_and_a_renewal_are_not_plan_changes(reason):
    assert charges_from_events([(PAID, _invoice(1, reason=reason))]) == {}


def test_a_plan_change_given_back_in_full_is_no_longer_listed():
    events = [
        (PAID, _invoice(1)),
        (REFUNDED, _invoice(1, status="refunded", refunded=True, refunded_amount=9996)),
    ]

    assert charges_from_events(events) == {}


def test_a_plan_change_given_back_in_part_lists_what_is_left():
    events = [
        (PAID, _invoice(1)),
        (REFUNDED, _invoice(1, status="partial_refund", refunded_amount=2000)),
    ]

    (charge,) = charges_from_events(events)["1"]
    assert (charge.amount, charge.refunded_amount, charge.outstanding_amount) == (9996, 2000, 7996)


def test_a_refunds_event_is_matched_by_its_invoice_whatever_else_it_says():
    # The refund's event needn't repeat why the invoice was raised, or how much was given back.
    refund = _invoice(1, status="refunded")
    del refund["data"]["attributes"]["billing_reason"]

    assert charges_from_events([(PAID, _invoice(1)), (REFUNDED, refund)]) == {}


def test_each_subscription_keeps_its_own_charges_oldest_first():
    events = [
        (PAID, _invoice(1, invoice_id="inv-a", total=1000)),
        (PAID, _invoice(2, invoice_id="inv-b", total=2000)),
        (PAID, _invoice(1, invoice_id="inv-c", total=3000, at=UPGRADED_AT + timedelta(days=1))),
        (PAID, _invoice(1, invoice_id="inv-d", reason="renewal", total=8900)),
    ]

    charges = charges_from_events(events)

    assert [c.invoice_id for c in charges["1"]] == ["inv-a", "inv-c"]
    assert [c.invoice_id for c in charges["2"]] == ["inv-b"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": None},
        {"data": {"id": "inv-1", "attributes": None}},
        {"data": {"id": "inv-1", "attributes": {"billing_reason": "updated", "total": 5}}},
        {"data": {"attributes": {"subscription_id": 1, "billing_reason": "updated", "total": 5}}},
    ],
)
def test_an_event_without_its_invoice_or_subscription_is_passed_over(payload):
    assert charges_from_events([(PAID, payload)]) == {}


@pytest.mark.parametrize("total", [None, "", "n/a", 0, -5])
def test_a_plan_change_that_charged_nothing_is_not_a_charge(total):
    # A downgrade's invoice, or one whose amount can't be read: nothing to give back.
    assert charges_from_events([(PAID, _invoice(1, total=total))]) == {}


def test_the_row_carries_what_is_still_to_give_back():
    charge = PlanChangeCharge("inv-1", 9996, 2000, "USD", UPGRADED_AT)

    assert charge.as_row() == {
        "invoice_id": "inv-1",
        "amount": 9996,
        "refunded_amount": 2000,
        "outstanding_amount": 7996,
        "currency": "USD",
        "paid_at": UPGRADED_AT,
    }


# --- on the database -------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    """A session on tables made inside a transaction that is rolled back."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[
                    model.__table__
                    for model in (Users, SubscriptionPlan, UserSubscription, Order, WebhookEvent)
                ],
                checkfirst=True,
            )
        )
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        await transaction.rollback()
    await engine.dispose()


async def _store(db, name, payload, *, minutes=0):
    db.add(
        WebhookEvent(
            event_id=f"evt-{uuid4().hex}",
            event_name=name,
            payload=payload,
            created_at=UPGRADED_AT + timedelta(minutes=minutes),
        )
    )
    await db.flush()


@pytest.mark.asyncio
async def test_the_stored_events_of_the_asked_subscriptions_are_read(db):
    mine, other, quiet = (uuid4().int % 10**9 for _ in range(3))
    await _store(db, PAID, _invoice(mine, invoice_id="inv-mine"))
    await _store(db, PAID, _invoice(mine, invoice_id="inv-first", reason="initial", total=8900))
    await _store(db, PAID, _invoice(other, invoice_id="inv-other", total=5000))
    await _store(db, "subscription_updated", _invoice(mine, invoice_id="inv-noise"))

    # Lemon Squeezy sends the id as a number; the subscription row holds it as text.
    charges = await plan_change_charges(db, [str(mine), str(quiet), None])

    assert list(charges) == [str(mine)]
    assert [(c.invoice_id, c.amount) for c in charges[str(mine)]] == [("inv-mine", 9996)]


@pytest.mark.asyncio
async def test_a_refund_stored_later_takes_the_charge_off(db):
    subscription = uuid4().int % 10**9
    await _store(db, PAID, _invoice(subscription))
    assert await plan_change_charges(db, [str(subscription)]) != {}

    await _store(
        db, REFUNDED, _invoice(subscription, status="refunded", refunded_amount=9996), minutes=5
    )

    assert await plan_change_charges(db, [str(subscription)]) == {}


@pytest.mark.asyncio
async def test_no_subscription_asks_nothing_of_the_database():
    assert await plan_change_charges(None, [None, ""]) == {}


def _order(order_id, subscription_id, *, at=UPGRADED_AT - timedelta(hours=1)):
    """What the lookup reads of an order: its ids and when it was paid."""
    return SimpleNamespace(
        lemonsqueezy_order_id=order_id,
        lemonsqueezy_subscription_id=subscription_id,
        ordered_at=at,
        created_at=at,
    )


@pytest.mark.asyncio
async def test_an_orders_charges_are_its_subscriptions(db):
    linked, unlinked, single = (str(uuid4().int % 10**9) for _ in range(3))
    await _store(db, PAID, _invoice(int(linked), invoice_id="inv-linked"))
    await _store(db, PAID, _invoice(int(unlinked), invoice_id="inv-unlinked", total=3300))

    # An order made before the subscription's id was kept on it: the subscription names it.
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    plan = SubscriptionPlan(name=f"growth-{uuid4().hex[:8]}", display_name="Growth")
    db.add_all([user, plan])
    await db.flush()
    db.add(
        UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            lemonsqueezy_subscription_id=unlinked,
            lemonsqueezy_order_id="ord-unlinked",
        )
    )
    await db.flush()

    orders = [
        _order("ord-linked", linked),
        _order("ord-unlinked", None),
        _order("ord-once", single),
        _order("ord-lifetime", None),
        None,  # a request whose order is gone
    ]

    charges = await plan_change_charges_for_orders(db, orders)

    assert {order: [c.invoice_id for c in found] for order, found in charges.items()} == {
        "ord-linked": ["inv-linked"],
        "ord-unlinked": ["inv-unlinked"],
    }


@pytest.mark.asyncio
async def test_a_plan_change_belongs_to_the_order_whose_period_it_was_paid_in(db):
    # The first month: bought, then upgraded. A month later the renewal, then another change.
    subscription = str(uuid4().int % 10**9)
    bought = UPGRADED_AT - timedelta(hours=1)
    renewed = bought + timedelta(days=30)
    await _store(db, PAID, _invoice(int(subscription), invoice_id="inv-first-month"))
    await _store(
        db,
        PAID,
        _invoice(
            int(subscription),
            invoice_id="inv-second-month",
            total=4000,
            at=renewed + timedelta(days=2),
        ),
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add(user)
    await db.flush()
    for order_id, at in (("ord-first", bought), ("ord-renewal", renewed)):
        db.add(
            Order(
                user_id=user.id,
                lemonsqueezy_order_id=f"{order_id}-{subscription}",
                lemonsqueezy_subscription_id=subscription,
                total=8900,
                ordered_at=at,
            )
        )
    await db.flush()

    # Asked about one order at a time, as the answer to a decision is, and about the page.
    first = _order(f"ord-first-{subscription}", subscription, at=bought)
    renewal = _order(f"ord-renewal-{subscription}", subscription, at=renewed)
    alone = await plan_change_charges_for_orders(db, [renewal])
    both = await plan_change_charges_for_orders(db, [first, renewal])

    assert {k: [c.invoice_id for c in v] for k, v in alone.items()} == {
        f"ord-renewal-{subscription}": ["inv-second-month"]
    }
    assert {k: [c.invoice_id for c in v] for k, v in both.items()} == {
        f"ord-first-{subscription}": ["inv-first-month"],
        f"ord-renewal-{subscription}": ["inv-second-month"],
    }


def _charge(invoice_id, paid_at):
    return PlanChangeCharge(invoice_id, 9996, 0, "USD", paid_at)


def test_a_period_runs_from_its_payment_to_the_next():
    bought = UPGRADED_AT - timedelta(hours=1)
    renewed = bought + timedelta(days=30)
    charges = [
        _charge("first-month", UPGRADED_AT),
        _charge("on-the-renewal", renewed),
        _charge("second-month", renewed + timedelta(days=3)),
        _charge("no-day", None),
    ]

    def ids(found):
        return [c.invoice_id for c in found]

    assert ids(in_its_period(charges, bought, [renewed])) == ["first-month"]
    assert ids(in_its_period(charges, renewed, [bought])) == [
        "on-the-renewal",
        "second-month",
        "no-day",  # an unknown day goes with the newest payment
    ]
    # Times with and without a zone are the same moments.
    assert ids(in_its_period(charges, bought.replace(tzinfo=None), [renewed])) == ["first-month"]
    # An order whose own time is unknown can't be placed in a period: nothing is held back.
    assert ids(in_its_period(charges, None, [])) == [c.invoice_id for c in charges]
    assert ids(in_its_period(charges, None, [renewed])) == [c.invoice_id for c in charges]


# --- on the admin's rows ---------------------------------------------------------------------


def _request(order_id="ord-1"):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        order_id=uuid4(),
        lemonsqueezy_order_id=order_id,
        requested_amount=8900,
        currency="USD",
        reason="Not what I needed",
        status=refund_routes.RefundRequestStatus.PENDING,
        admin_note=None,
        reviewed_at=None,
        refund_id=None,
        created_at=now,
        user=SimpleNamespace(email="buyer@example.com", full_name="Ana"),
        order=SimpleNamespace(
            product_name="Growth",
            total=8900,
            status=refund_routes.OrderStatus.PAID,
            lemonsqueezy_order_id=order_id,
            lemonsqueezy_subscription_id="2590065",
        ),
    )


def test_a_requests_row_names_the_plan_change_the_refund_leaves_out():
    charge = PlanChangeCharge("inv-1", 9996, 0, "USD", UPGRADED_AT)

    row = RefundRequestRow(**refund_routes._admin_request_row(_request(), 0, [charge]))

    (listed,) = row.plan_change_charges
    assert (listed.invoice_id, listed.amount, listed.outstanding_amount) == ("inv-1", 9996, 9996)
    assert listed.paid_at == UPGRADED_AT
    assert row.refundable_amount == 8900  # the order's own, unchanged


def test_a_row_without_a_plan_change_lists_none():
    row = RefundRequestRow(**refund_routes._admin_request_row(_request()))

    assert row.plan_change_charges == []
    assert RefundableOrderRow.model_fields["plan_change_charges"].default == []
