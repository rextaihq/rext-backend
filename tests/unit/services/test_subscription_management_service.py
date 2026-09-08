"""Unit tests for SubscriptionManagementService."""

from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.user_models.users import Users
from src.api.schema.subscription import (
    AdminSubscriptionAssignRequest,
    AdminSubscriptionExtendRequest,
    AdminUsageResetRequest,
)
from src.services.subscription_management_service import SubscriptionManagementService


@pytest.mark.asyncio
async def test_assign_subscription_creates_entry():
    from unittest.mock import Mock

    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = Mock()  # Changed to regular Mock since add() is not async
    service = SubscriptionManagementService(mock_db)

    user = Users(id=uuid4(), email="user@example.com", display_name="user")
    plan = SubscriptionPlan(id=uuid4(), name="pro", display_name="Pro Plan")

    service._get_user_or_404 = AsyncMock(return_value=user)
    service._get_active_plan = AsyncMock(return_value=plan)
    service._ensure_no_active_subscription = AsyncMock()

    payload = AdminSubscriptionAssignRequest(
        user_id=str(user.id),
        plan_id=str(plan.id),
        status=SubscriptionStatus.ACTIVE,
        billing_period="monthly",
        trial_days=0,
    )

    result = await service.assign_subscription(admin_user_id=uuid4(), payload=payload)

    service._ensure_no_active_subscription.assert_awaited_once()
    mock_db.add.assert_called_once()  # Changed to assert_called_once() for non-async
    mock_db.flush.assert_awaited_once()
    mock_db.refresh.assert_awaited_once()
    assert result["subscription"]["plan_name"] == "pro"


@pytest.mark.asyncio
async def test_extend_subscription_updates_dates():
    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    service = SubscriptionManagementService(mock_db)

    subscription = UserSubscription(
        user_id=uuid4(),
        plan_id=uuid4(),
        status=SubscriptionStatus.TRIAL,
        billing_period="monthly",
    )
    subscription.id = uuid4()
    subscription.end_date = datetime.now(timezone.utc)
    subscription.trial_end_date = datetime.now(timezone.utc)

    service._get_subscription_or_404 = AsyncMock(return_value=subscription)

    payload = AdminSubscriptionExtendRequest(extend_days=10, reason="courtesy")

    result = await service.extend_subscription(admin_user_id=uuid4(), subscription_id=subscription.id, payload=payload)

    service._get_subscription_or_404.assert_awaited_once()
    assert "subscription" in result
    assert subscription.end_date is not None
    assert subscription.trial_end_date is not None


@pytest.mark.asyncio
async def test_reset_usage_resets_counters():
    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    service = SubscriptionManagementService(mock_db)

    subscription = UserSubscription(
        user_id=uuid4(),
        plan_id=uuid4(),
        status=SubscriptionStatus.ACTIVE,
        billing_period="monthly",
    )
    subscription.id = uuid4()
    subscription.current_api_calls = 42

    service._get_subscription_or_404 = AsyncMock(return_value=subscription)

    payload = AdminUsageResetRequest(reset_api_calls=True, reason="test")

    result = await service.reset_usage(admin_user_id=uuid4(), subscription_id=subscription.id, payload=payload)

    assert result["subscription"]["current_api_calls"] == 0
    service._get_subscription_or_404.assert_awaited_once()
