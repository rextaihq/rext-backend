"""The API-call quota's two columns until they are dropped (rext-control#369, step 1): still
mapped and still written, so the release before this one works on a rollback, and no longer
part of what the API answers with."""

import pytest

from scripts.seeds.seed_subscription_plans import PLANS
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription

pytestmark = pytest.mark.unit


def test_the_two_columns_stay_mapped_with_their_defaults():
    assert UserSubscription.__table__.c.current_api_calls.default.arg == 0
    assert SubscriptionPlan.__table__.c.max_api_calls_per_month.default.arg == 10000


def test_a_seeded_plan_still_has_its_quota():
    # The seed inserts with raw SQL, where the mapped default doesn't apply.
    assert all(isinstance(plan.get("max_api_calls_per_month"), int) for plan in PLANS)


def test_neither_is_part_of_an_answer():
    subscription = UserSubscription(current_api_calls=7)
    plan = SubscriptionPlan(name="starter", max_api_calls_per_month=5000)

    assert "current_api_calls" not in subscription.to_dict(include_nulls=True)
    assert "max_api_calls_per_month" not in plan.to_dict(include_nulls=True)
    assert plan.to_dict(exclude=["name"]).get("name") is None
