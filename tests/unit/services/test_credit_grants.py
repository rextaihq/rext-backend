"""Credit grants: a promotion's bonus, given once, spent first, expiring."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from scripts.seeds.seed_promotions import LAUNCH_PROMOTION
from src.services.credit_grants import (
    bonus_summary,
    promotion_applies,
    promotion_bonus,
    split_cost,
)
from src.services.refund_request_service import RefundRequestService
from src.services.usage_tracking_service import UsageTrackingService

LAUNCH = SimpleNamespace(**LAUNCH_PROMOTION)
INSIDE = LAUNCH.starts_at + timedelta(days=2)


def _promotion(**changes):
    return SimpleNamespace(**{**LAUNCH_PROMOTION, **changes})


class FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row

    def unique(self):
        return self


def _grant(remaining, amount=None, expires_in_days=30, promotion=LAUNCH, source="promotion"):
    return SimpleNamespace(
        remaining=remaining,
        amount=amount if amount is not None else remaining,
        expires_at=(
            None
            if expires_in_days is None
            else datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        ),
        promotion=promotion,
        source=source,
    )


# --- which subscriptions a promotion applies to ------------------------------


def test_a_subscription_started_inside_the_window_qualifies():
    assert promotion_applies(LAUNCH, LAUNCH.starts_at, "growth", "monthly")
    assert promotion_applies(LAUNCH, INSIDE, "pro", "yearly")
    assert promotion_applies(LAUNCH, LAUNCH.ends_at - timedelta(seconds=1), "growth", "monthly")


def test_a_subscription_started_outside_the_window_does_not():
    assert not promotion_applies(
        LAUNCH, LAUNCH.starts_at - timedelta(seconds=1), "growth", "monthly"
    )
    assert not promotion_applies(LAUNCH, LAUNCH.ends_at, "growth", "monthly")


def test_the_providers_naive_utc_dates_are_read_as_utc():
    assert promotion_applies(LAUNCH, INSIDE.replace(tzinfo=None), "growth", "monthly")


def test_an_inactive_promotion_applies_to_nobody():
    assert not promotion_applies(_promotion(is_active=False), INSIDE, "growth", "monthly")


def test_a_promotion_can_be_limited_to_some_plans_and_periods():
    limited = _promotion(plan_names=["pro", "agency"], billing_periods=["yearly"])

    assert promotion_applies(limited, INSIDE, "pro", "yearly")
    assert not promotion_applies(limited, INSIDE, "growth", "yearly")
    assert not promotion_applies(limited, INSIDE, "pro", "monthly")


# --- the bonus ---------------------------------------------------------------


def test_double_credits_means_one_months_credits_on_top_until_the_first_period_ends():
    period_end = INSIDE + timedelta(days=31)

    bonus = promotion_bonus(LAUNCH, 1000, INSIDE, period_end)

    assert bonus.amount == 1000
    assert bonus.expires_at == period_end


def test_a_yearly_plans_bonus_ends_after_its_first_month():
    bonus = promotion_bonus(LAUNCH, 2400, INSIDE, INSIDE + timedelta(days=365))

    assert bonus.amount == 2400
    assert bonus.expires_at == INSIDE.replace(month=INSIDE.month + 1)  # a month on, not a year


def test_a_fixed_bonus_is_that_many_credits():
    fixed = _promotion(credit_multiplier=None, bonus_credits=250)

    assert promotion_bonus(fixed, 1000, INSIDE, None).amount == 250


@pytest.mark.parametrize("monthly", [None, 0])
def test_a_multiplier_on_a_plan_without_monthly_credits_gives_nothing(monthly):
    assert promotion_bonus(LAUNCH, monthly, INSIDE, None) is None


# --- spending: expiring grants, then the monthly credits, then lasting grants -


def test_a_cost_is_taken_from_the_expiring_grants_first_in_order():
    assert split_cost(12, [5, 10], 100, []) == ([5, 7], 0, [])
    assert split_cost(20, [5, 10], 100, []) == ([5, 10], 5, [])
    assert split_cost(3, [], 100, []) == ([], 3, [])


def test_grants_without_an_expiry_are_spent_after_the_monthly_credits():
    assert split_cost(3, [], 100, [50]) == ([], 3, [0])
    assert split_cost(120, [5], 100, [10, 50]) == ([5], 100, [10, 5])
    assert split_cost(7, [], 0, [5, 50]) == ([], 0, [5, 2])


def test_a_cost_larger_than_everything_is_refused():
    assert split_cost(116, [5, 10], 100, []) is None
    assert split_cost(1, [], 0, []) is None
    assert split_cost(166, [5, 10], 100, [50]) is None


def test_a_negative_monthly_balance_gives_nothing():
    assert split_cost(5, [], -10, [5]) == ([], 0, [5])


@pytest.mark.asyncio
async def test_consume_credits_spends_the_bonus_before_the_monthly_credits(monkeypatch):
    plan = SimpleNamespace(is_trial_plan=False, credits_per_month=1000)
    subscription = SimpleNamespace(
        id=uuid4(),
        plan=plan,
        current_credits=1000,
        credits_reset_date=datetime.now(timezone.utc) + timedelta(days=20),
        grace_period_end=None,
        status="active",
    )
    bonus = _grant(10, amount=1000)
    monkeypatch.setattr(
        "src.services.usage_tracking_service.live_grants", AsyncMock(return_value=[bonus])
    )
    db = AsyncMock()
    db.execute.return_value = FakeResult(subscription)

    assert await UsageTrackingService(db).consume_credits(uuid4(), 15) is True

    assert bonus.remaining == 0
    assert subscription.current_credits == 995


@pytest.mark.asyncio
async def test_the_balance_counts_the_unexpired_bonus(monkeypatch):
    subscription = SimpleNamespace(id=uuid4(), current_credits=400)
    monkeypatch.setattr(
        "src.services.usage_tracking_service.grant_balance", AsyncMock(return_value=400)
    )
    db = AsyncMock()
    db.execute.return_value = FakeResult(subscription)

    assert await UsageTrackingService(db).get_credit_balance(uuid4()) == 800


# --- what the dashboard shows -----------------------------------------------


def test_the_summary_names_the_bonus_and_its_end():
    grant = _grant(600, amount=1000)

    summary = bonus_summary([grant])

    assert summary["label"] == "Launch bonus"
    assert summary["promotion"] == "launch-2026-10"
    assert summary["credits"] == 600
    assert summary["granted"] == 1000
    assert summary["expires_at"] == grant.expires_at.isoformat()


def test_no_live_grant_means_no_summary():
    assert bonus_summary([]) is None


def test_the_bonus_summary_leaves_out_added_credits():
    added = _grant(50, promotion=None, expires_in_days=None, source="admin")

    assert bonus_summary([added]) is None
    assert bonus_summary([_grant(600, amount=1000), added])["credits"] == 600


# --- refunds ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_bonus_credits_spent_count_as_used_for_the_refund_rule(monkeypatch):
    # 1,000 monthly credits untouched, 900 bonus credits spent: 900 are used, and
    # they lower the refundable credits as monthly credits would (100 left).
    plan = SimpleNamespace(credits_per_month=1000, is_trial_plan=False)
    subscription = SimpleNamespace(
        id=uuid4(), plan=plan, current_credits=1000, subscription_metadata={}
    )
    ordered_at = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
    order = SimpleNamespace(
        subscription_id=None,
        user_id=uuid4(),
        total=8900,
        lemonsqueezy_order_id="1",
        ordered_at=ordered_at,
        created_at=ordered_at,
    )
    used = AsyncMock(return_value=900)
    monkeypatch.setattr("src.services.refund_request_service.grant_credits_used", used)
    db = AsyncMock()
    db.execute.return_value = FakeResult(subscription)

    usage = await RefundRequestService(db)._get_credit_usage_details(order)

    assert usage["used"] == 900
    assert usage["unused"] == 100
    assert usage["max_partial_refund_cents"] == 890
    # Only grants of the refunded order's subscription and period count.
    assert used.await_args.args[1] == subscription.id
    assert used.await_args.kwargs["since"] == ordered_at
    assert used.await_args.kwargs["until"] == ordered_at + timedelta(days=1)
    assert used.await_args.kwargs["order_id"] == "1"


# --- webhook ordering ---------------------------------------------------------


@pytest.mark.asyncio
async def test_a_first_payment_before_its_subscription_is_retried():
    # The first payment can carry the bonus of a subscription created unpaid: it
    # must be delivered again once the subscription exists, not dropped.
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_payment_success,
    )

    db = AsyncMock()
    db.execute.return_value = FakeResult(None)
    invoice = {
        "event_id": "e1",
        "data": {
            "type": "subscription-invoices",
            "attributes": {"subscription_id": 77, "billing_reason": "initial", "status": "paid"},
        },
    }

    with pytest.raises(ValueError, match="not found in payment_success"):
        await handle_subscription_payment_success(invoice, None, db)


@pytest.mark.asyncio
async def test_a_renewal_before_its_subscription_is_retried_too():
    # F11 (revnix/rext-control#336): credits come only with a payment, so no payment
    # is dropped; the reprocessing job runs it again once the row exists.
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_payment_success,
    )

    db = AsyncMock()
    db.execute.return_value = FakeResult(None)
    invoice = {
        "event_id": "e2",
        "data": {
            "type": "subscription-invoices",
            "attributes": {"subscription_id": 77, "billing_reason": "renewal", "status": "paid"},
        },
    }

    with pytest.raises(ValueError, match="not found in payment_success"):
        await handle_subscription_payment_success(invoice, None, db)


@pytest.mark.asyncio
async def test_the_first_payment_judges_the_window_by_the_subscriptions_start(monkeypatch):
    # A trial that converts later pays its first invoice after the window; the
    # subscription's start, inside the window, is what decides.
    from src.services.webhook_handlers import subscription_handlers

    started = INSIDE.replace(tzinfo=None)
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=uuid4(),
        status="active",
        start_date=started,
        # A trial: it converts with this payment, so its month comes now.
        trial_end_date=started + timedelta(days=7),
        billing_period=SimpleNamespace(value="monthly"),
        renews_at=None,
        plan=None,
        grace_period_end=None,
        current_api_calls=0,
        lemonsqueezy_order_id="555",
        # What the ordering checks read (F11): no state stored yet, no payment credited.
        provider_updated_at=None,
        subscription_metadata={},
        end_date=None,
    )
    plan = SimpleNamespace(is_trial_plan=False, credits_per_month=1000, name="growth")
    grant = AsyncMock(return_value=1000)
    monkeypatch.setattr(subscription_handlers, "grant_promotion_bonus", grant)
    db = AsyncMock()
    db.execute.side_effect = [FakeResult(subscription), FakeResult(plan)] + [FakeResult(None)] * 10
    db.scalar.return_value = False  # the order has no refund
    invoice = {
        "event_id": "e3",
        "data": {
            "type": "subscription-invoices",
            "attributes": {
                "subscription_id": 77,
                "billing_reason": "initial",
                "status": "paid",
                "created_at": "2026-10-20T10:00:00.000000Z",
            },
        },
    }

    try:
        await subscription_handlers.handle_subscription_payment_success(invoice, None, db)
    except Exception:  # noqa: BLE001 - later bookkeeping is not what this test is about
        pass

    assert grant.await_args is not None
    assert grant.await_args.args[4] == started
    # ...while the bonus runs from the payment itself.
    assert grant.await_args.kwargs["paid_from"] == datetime(2026, 10, 20, 10)
    # ...whose own moments may hold it inside the window too (a trial begun before the offer).
    assert datetime(2026, 10, 20, 10) in grant.await_args.kwargs["first_payment"]
    # ...and the grant records the order that started the subscription.
    assert grant.await_args.kwargs["order_id"] == "555"


@pytest.mark.asyncio
async def test_without_a_bonus_the_refund_figures_are_unchanged(monkeypatch):
    plan = SimpleNamespace(credits_per_month=1000, is_trial_plan=False)
    subscription = SimpleNamespace(
        id=uuid4(), plan=plan, current_credits=600, subscription_metadata={}
    )
    ordered_at = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
    order = SimpleNamespace(
        subscription_id=None,
        user_id=uuid4(),
        total=8900,
        lemonsqueezy_order_id="1",
        ordered_at=ordered_at,
        created_at=ordered_at,
    )
    monkeypatch.setattr(
        "src.services.refund_request_service.grant_credits_used", AsyncMock(return_value=0)
    )
    db = AsyncMock()
    db.execute.return_value = FakeResult(subscription)

    usage = await RefundRequestService(db)._get_credit_usage_details(order)

    assert (usage["used"], usage["unused"], usage["max_partial_refund_cents"]) == (400, 600, 5340)


def test_a_trials_bonus_runs_from_its_first_payment():
    # Started inside the window on a trial, paid 14 days later: the bonus lasts
    # the paid month, not what is left of a month counted from the trial start.
    paid_from = INSIDE + timedelta(days=14)

    bonus = promotion_bonus(LAUNCH, 1000, paid_from, paid_from + timedelta(days=30))

    assert bonus.expires_at == paid_from + timedelta(days=30)


@pytest.mark.asyncio
async def test_a_partial_refund_forfeits_the_unspent_bonus(monkeypatch):
    # An unused 1,000-credit bonus and untouched monthly credits: a small partial
    # refund takes the bonus back (it came with the purchase) and reports it.
    plan = SimpleNamespace(credits_per_month=1000, is_trial_plan=False, name="growth")
    subscription = SimpleNamespace(
        id=uuid4(),
        plan=plan,
        current_credits=1000,
        credits_reset_date=datetime.now(timezone.utc) + timedelta(days=20),
        subscription_metadata={},
        updated_at=None,
    )
    monkeypatch.setattr(
        "src.services.order_service.OrderService.is_latest_order", AsyncMock(return_value=True)
    )
    forfeit = AsyncMock(return_value=1000)
    monkeypatch.setattr("src.services.usage_tracking_service.forfeit_grants", forfeit)
    db = AsyncMock()
    db.execute.return_value = FakeResult(subscription)

    adjustment = await UsageTrackingService(db).reconcile_partial_refund_credits(
        user_id=uuid4(), lemonsqueezy_order_id="1", refunded_total=100, original_amount=8900
    )

    assert adjustment["bonus_forfeited"] == 1000
    assert forfeit.await_args.args[1] == subscription.id


@pytest.mark.asyncio
async def test_a_second_partial_refund_cannot_reuse_the_same_cap(monkeypatch):
    # 900 bonus credits spent; a first partial refund already cut 100 monthly
    # credits from this order. Nothing refundable is left for another request.
    plan = SimpleNamespace(credits_per_month=1000, is_trial_plan=False)
    subscription = SimpleNamespace(
        id=uuid4(),
        plan=plan,
        current_credits=900,
        subscription_metadata={"refund_credit_reduction": {"order_id": "1", "credits": 100}},
    )
    ordered_at = datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
    order = SimpleNamespace(
        subscription_id=None,
        user_id=uuid4(),
        total=8900,
        lemonsqueezy_order_id="1",
        ordered_at=ordered_at,
        created_at=ordered_at,
    )
    monkeypatch.setattr(
        "src.services.refund_request_service.grant_credits_used", AsyncMock(return_value=900)
    )
    db = AsyncMock()
    db.execute.return_value = FakeResult(subscription)

    usage = await RefundRequestService(db)._get_credit_usage_details(order)

    assert usage["unused"] == 0
    assert usage["max_partial_refund_cents"] == 0


@pytest.mark.asyncio
async def test_a_retried_first_payment_after_a_refund_keeps_the_reduced_credits(monkeypatch):
    # created -> partial refund (credits cut to 400) -> the first payment retried:
    # the payment must not hand the refunded credits back, nor grant the bonus.
    from src.services.webhook_handlers import subscription_handlers

    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=uuid4(),
        status="active",
        start_date=INSIDE.replace(tzinfo=None),
        billing_period=SimpleNamespace(value="monthly"),
        renews_at=None,
        plan=None,
        grace_period_end=None,
        current_api_calls=0,
        current_credits=400,
        lemonsqueezy_order_id="555",
    )
    plan = SimpleNamespace(is_trial_plan=False, credits_per_month=1000, name="growth")
    grant = AsyncMock(return_value=1000)
    monkeypatch.setattr(subscription_handlers, "grant_promotion_bonus", grant)
    db = AsyncMock()
    db.execute.side_effect = [FakeResult(subscription), FakeResult(plan)] + [FakeResult(None)] * 10
    db.scalar.return_value = True  # the order has a refund
    invoice = {
        "event_id": "e4",
        "data": {
            "type": "subscription-invoices",
            "attributes": {"subscription_id": 77, "billing_reason": "initial", "status": "paid"},
        },
    }

    try:
        await subscription_handlers.handle_subscription_payment_success(invoice, None, db)
    except Exception:  # noqa: BLE001 - later bookkeeping is not what this test is about
        pass

    assert subscription.current_credits == 400
    assert grant.await_args is None
