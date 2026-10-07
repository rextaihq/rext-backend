"""An ended trial is reported as such, whether or not the daily expiry job has closed it yet."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.api.models.subscription_models.subscriptions import SubscriptionStatus
from src.services.subscription_service import trial_has_ended

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
TRIAL_PLAN = SimpleNamespace(is_trial_plan=True)
PAID_PLAN = SimpleNamespace(is_trial_plan=False)


def _subscription(
    status, plan=TRIAL_PLAN, trial_end_date=NOW - timedelta(days=1), lemonsqueezy_id=None
):
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        plan=plan,
        trial_end_date=trial_end_date,
        lemonsqueezy_subscription_id=lemonsqueezy_id,
    )


def test_a_trial_the_job_expired_has_ended():
    trial = _subscription(SubscriptionStatus.EXPIRED)

    assert trial_has_ended(trial, None, NOW) is True


def test_a_trial_past_its_end_date_has_ended_before_the_job_runs():
    trial = _subscription(SubscriptionStatus.TRIAL)

    # Until the job runs, a TRIAL row still grants access, so it is also the granting one.
    assert trial_has_ended(trial, trial, NOW) is True


def test_a_paid_plan_trial_that_was_never_paid_has_ended():
    # subscribe() starts a paid plan with 14 days of TRIAL; the job expires it unpaid.
    trial = _subscription(SubscriptionStatus.EXPIRED, plan=PAID_PLAN)

    assert trial_has_ended(trial, None, NOW) is True


def test_a_running_trial_has_not_ended():
    trial = _subscription(SubscriptionStatus.TRIAL, trial_end_date=NOW + timedelta(days=3))

    assert trial_has_ended(trial, trial, NOW) is False


def test_a_trial_without_an_end_date_has_not_ended():
    trial = _subscription(SubscriptionStatus.TRIAL, trial_end_date=None)

    assert trial_has_ended(trial, trial, NOW) is False


def test_a_plan_bought_after_the_trial_replaces_it():
    trial = _subscription(SubscriptionStatus.EXPIRED)
    paid = _subscription(SubscriptionStatus.ACTIVE, plan=PAID_PLAN, trial_end_date=None)

    assert trial_has_ended(trial, paid, NOW) is False


def test_a_paid_trial_that_ended_later_is_not_an_ended_trial():
    # Converted with a Lemon Squeezy subscription, then cancelled and expired.
    paid = _subscription(SubscriptionStatus.EXPIRED, plan=PAID_PLAN, lemonsqueezy_id="ls_123")

    assert trial_has_ended(paid, None, NOW) is False


@pytest.mark.parametrize(
    "status", [SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED, SubscriptionStatus.ACTIVE]
)
def test_a_paid_subscription_without_a_trial_is_never_an_ended_trial(status):
    paid = _subscription(status, plan=PAID_PLAN, trial_end_date=None)

    assert trial_has_ended(paid, None, NOW) is False


def test_no_subscription_at_all_is_not_an_ended_trial():
    assert trial_has_ended(None, None, NOW) is False
