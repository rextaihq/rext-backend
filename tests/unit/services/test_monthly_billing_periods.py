from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.services.subscription_service import SubscriptionService
from src.utils.datetime_utils import add_months, next_billing_anchor, parse_provider_datetime


@pytest.mark.unit
class TestMonthlyBillingPeriods:
    """Test calendar-based monthly billing periods (Test 1-8)"""

    def test_add_months_normal(self):
        """Test 1 & 2: Normal monthly billing periods"""
        dt = datetime(2023, 9, 10, 15, 30, tzinfo=timezone.utc)
        next_month = add_months(dt, 1)
        assert next_month.year == 2023
        assert next_month.month == 10
        assert next_month.day == 10

        next_next_month = add_months(next_month, 1)
        assert next_next_month.year == 2023
        assert next_next_month.month == 11
        assert next_next_month.day == 10

    def test_add_months_edge_cases(self):
        """Test 3: Jan 31 edge cases"""
        # Jan 31 -> Feb 28 (non-leap year)
        dt1 = datetime(2023, 1, 31, tzinfo=timezone.utc)
        res1 = add_months(dt1, 1)
        assert res1.month == 2
        assert res1.day == 28

        # Jan 31 -> Feb 29 (leap year)
        dt2 = datetime(2024, 1, 31, tzinfo=timezone.utc)
        res2 = add_months(dt2, 1)
        assert res2.month == 2
        assert res2.day == 29

        # Leap year Feb 29 -> next year Feb 28
        res3 = add_months(res2, 12)
        assert res3.year == 2025
        assert res3.month == 2
        assert res3.day == 28

    def test_calendar_progression_sep_to_dec(self):
        """Sep 10 -> Oct 10 -> Nov 10 -> Dec 10, no 30-day drift."""
        d = datetime(2025, 9, 10, 12, 0, tzinfo=timezone.utc)
        for expected in ((2025, 10, 10), (2025, 11, 10), (2025, 12, 10), (2026, 1, 10)):
            d = add_months(d, 1)
            assert (d.year, d.month, d.day) == expected

    def test_next_billing_anchor_advances_one_period(self):
        """Anchor slightly in the past -> next single calendar period."""
        now = datetime(2025, 10, 10, 0, 5, tzinfo=timezone.utc)
        anchor = datetime(2025, 10, 10, 0, 0, tzinfo=timezone.utc)
        assert next_billing_anchor(anchor, now) == datetime(2025, 11, 10, 0, 0, tzinfo=timezone.utc)

    def test_next_billing_anchor_stale_catch_up(self):
        """A reset date several months behind jumps straight past `now`,
        preserving the billing-day anchor (computed from the original anchor)."""
        anchor = datetime(2025, 1, 31, 0, 0, tzinfo=timezone.utc)
        now = datetime(2025, 5, 15, 0, 0, tzinfo=timezone.utc)
        result = next_billing_anchor(anchor, now)
        # add_months(Jan31, 4) -> May 31 (first period end strictly after May 15)
        assert result == datetime(2025, 5, 31, 0, 0, tzinfo=timezone.utc)
        assert result > now

    def test_next_billing_anchor_jan31_end_of_month(self):
        anchor = datetime(2025, 1, 31, tzinfo=timezone.utc)
        now = datetime(2025, 2, 1, tzinfo=timezone.utc)
        # Feb has no 31st -> clamp to Feb 28
        assert next_billing_anchor(anchor, now) == datetime(2025, 2, 28, tzinfo=timezone.utc)

    def test_next_billing_anchor_handles_naive_anchor(self):
        """Naive anchor + aware now must not raise, result stays naive."""
        anchor = datetime(2025, 10, 10, 0, 0)  # naive
        now = datetime(2025, 10, 11, 0, 0, tzinfo=timezone.utc)
        result = next_billing_anchor(anchor, now)
        assert result.tzinfo is None
        assert result == datetime(2025, 11, 10, 0, 0)

    def test_parse_provider_datetime(self):
        assert parse_provider_datetime(None) is None
        assert parse_provider_datetime("2025-10-10T00:00:00.000000Z") == datetime(
            2025, 10, 10, 0, 0
        )
        # already offset form
        assert parse_provider_datetime("2025-10-10T00:00:00+00:00") == datetime(2025, 10, 10, 0, 0)
        assert parse_provider_datetime("2025-10-10T02:00:00+02:00") == datetime(2025, 10, 10, 0, 0)

    async def test_cancellation_before_period_end(self, monkeypatch):
        """Test 5: Cancellation before period end"""

        class MockUser:
            id = uuid4()

        user = MockUser()
        plan = SubscriptionPlan(id=uuid4(), name="pro", display_name="Pro Plan", price_monthly=1000)

        now = datetime.now(timezone.utc)
        future_date = now + timedelta(days=15)

        # Create active subscription
        sub = UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            lemonsqueezy_subscription_id="sub_123",
            start_date=now,
            renews_at=future_date,
            usage_reset_date=future_date,
        )
        # Mock payment provider cancel
        mock_db = AsyncMock()
        service = SubscriptionService(mock_db)
        service.get_subscription_by_user = AsyncMock(return_value=sub)

        class MockPaymentProvider:
            async def cancel_subscription(self, subscription_id, at_period_end):
                pass

        service.payment_provider = MockPaymentProvider()

        # Cancel subscription deferred
        updated_sub = await service.cancel(
            user_id=user.id, cancel_immediately=False, fail_on_provider_error=False
        )

        assert updated_sub.status == SubscriptionStatus.CANCELLED
        assert updated_sub.cancel_at_period_end is True
        assert updated_sub.end_date == future_date

        # Verify access is still granted (get_subscription_by_user returns it)
        active_sub = await service.get_subscription_by_user(user.id)
        assert active_sub is not None
        assert active_sub.id == sub.id

    async def test_daily_reset_task_is_calendar_anchored(self, monkeypatch):
        """Test 4: the scheduled daily task resets api calls + credits and
        advances the reset dates by a calendar month (no 30-day drift, no
        re-basing from now)."""
        from src.api.tasks import subscription_tasks

        now = datetime.now(timezone.utc)
        original_usage_anchor = now - timedelta(hours=2)
        original_credit_anchor = now - timedelta(hours=2)

        plan = SubscriptionPlan(
            id=uuid4(),
            name="pro",
            display_name="Pro",
            price_monthly=1000,
            is_trial_plan=False,
            credits_per_month=500,
        )
        sub = UserSubscription(
            user_id=uuid4(),
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            current_credits=1,
            usage_reset_date=original_usage_anchor,
            credits_reset_date=original_credit_anchor,
        )
        sub.plan = plan

        class FakeResult:
            def scalars(self):
                return self

            def all(self):
                return [sub]

        class FakeDB:
            async def execute(self, *a, **k):
                return FakeResult()

            async def commit(self):
                pass

            async def rollback(self):
                pass

        class FakeCtx:
            async def __aenter__(self):
                return FakeDB()

            async def __aexit__(self, *a):
                return False

        monkeypatch.setattr(subscription_tasks, "get_async_db_context", lambda: FakeCtx())

        result = await subscription_tasks.reset_monthly_usage()

        assert sub.current_credits == 500
        assert sub.usage_reset_date == next_billing_anchor(original_usage_anchor, now)
        assert sub.credits_reset_date == next_billing_anchor(original_credit_anchor, now)
        # calendar month, not now + 30 days
        assert sub.usage_reset_date != now + timedelta(days=30)
        assert result["subscriptions_reset"] == 1
        assert result["credits_reset"] == 1

    async def test_immediate_cancellation(self):
        """Test 6: Immediate cancellation"""

        class MockUser:
            id = uuid4()

        user = MockUser()
        plan = SubscriptionPlan(id=uuid4(), name="pro", display_name="Pro Plan", price_monthly=1000)

        now = datetime.now(timezone.utc)
        future_date = now + timedelta(days=15)

        sub = UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.MONTHLY,
            lemonsqueezy_subscription_id="sub_123",
            start_date=now,
            renews_at=future_date,
        )
        mock_db = AsyncMock()
        service = SubscriptionService(mock_db)
        service.get_subscription_by_user = AsyncMock(return_value=sub)

        class MockPaymentProvider:
            async def cancel_subscription(self, subscription_id, at_period_end):
                pass

        service.payment_provider = MockPaymentProvider()

        # Cancel immediately: Lemon Squeezy bills this one, so it runs to the paid
        # period's end (founder decision on F12, revnix/rext-control#337).
        updated_sub = await service.cancel(
            user_id=user.id, cancel_immediately=True, fail_on_provider_error=False
        )

        assert updated_sub.status == SubscriptionStatus.CANCELLED
        assert updated_sub.cancel_at_period_end is True
        assert updated_sub.end_date == future_date

        # A subscription Lemon Squeezy doesn't bill still ends now.
        sub.lemonsqueezy_subscription_id = None
        sub.status = SubscriptionStatus.ACTIVE
        updated_sub = await service.cancel(
            user_id=user.id, cancel_immediately=True, fail_on_provider_error=False
        )

        assert updated_sub.cancel_at_period_end is False
        # Time comparisons can be slightly off in tests, check if close
        diff = abs((updated_sub.end_date - datetime.now(timezone.utc)).total_seconds())
        assert diff < 2.0  # Within 2 seconds
