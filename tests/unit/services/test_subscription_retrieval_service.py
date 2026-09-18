"""Unit tests for SubscriptionRetrievalService."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.services.subscription_retrieval_service import SubscriptionRetrievalService


class FakeResult:
    def __init__(self, *, first=None, all_=None, scalar=None):
        self._first = first
        self._all = all_ or []
        self._scalar = scalar

    def first(self):
        return self._first

    def all(self):
        return self._all

    def scalar(self):
        return self._scalar


@pytest.mark.asyncio
async def test_list_subscriptions_returns_formatted_data():
    mock_db = AsyncMock()
    service = SubscriptionRetrievalService(mock_db)

    user = Users(id=uuid4(), email="user@example.com", username="user")
    plan = SubscriptionPlan(id=uuid4(), name="pro", display_name="Pro Plan")
    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        billing_period="monthly",
    )

    mock_db.execute.side_effect = [
        FakeResult(scalar=1),
        FakeResult(all_=[(subscription, user, plan)]),
    ]

    result = await service.list_subscriptions(
        status_filter=None,
        plan_id=None,
        user_email=None,
        limit=10,
        offset=0,
    )

    assert result["data"]["total"] == 1
    assert result["data"]["subscriptions"][0]["plan_name"] == "pro"


@pytest.mark.asyncio
async def test_get_subscription_returns_details():
    mock_db = AsyncMock()
    service = SubscriptionRetrievalService(mock_db)

    user = Users(id=uuid4(), email="user@example.com", username="user", status="active")
    plan = SubscriptionPlan(id=uuid4(), name="pro", display_name="Pro Plan")
    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        billing_period="monthly",
    )
    subscription_id = uuid4()

    mock_db.execute.return_value = FakeResult(first=(subscription, user, plan))

    result = await service.get_subscription(subscription_id)

    assert result["data"]["user"]["email"] == "user@example.com"
    assert result["data"]["plan"]["name"] == "pro"
