"""Unit tests for SubscriptionAnalyticsService."""

from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from src.api.models.subscription_models.subscriptions import SubscriptionStatus
from src.services.subscription_analytics_service import SubscriptionAnalyticsService


@pytest.mark.asyncio
async def test_get_subscription_stats_aggregates_helpers():
    mock_db = AsyncMock()
    service = SubscriptionAnalyticsService(mock_db)

    counts = {
        SubscriptionStatus.ACTIVE: 5,
        SubscriptionStatus.TRIAL: 3,
        SubscriptionStatus.CANCELLED: 1,
        SubscriptionStatus.EXPIRED: 1,
        SubscriptionStatus.SUSPENDED: 0,
    }

    service._count_by_status = AsyncMock(return_value=counts)
    service._count_all_subscriptions = AsyncMock(return_value=10)
    service._calculate_mrr = AsyncMock(return_value=120.0)
    service._count_cancellations = AsyncMock(return_value=2)
    service._count_trials_ever = AsyncMock(return_value=6)
    service._count_converted_trials = AsyncMock(return_value=4)

    result = await service.get_subscription_stats()

    assert result["data"]["total_subscriptions"] == 10
    assert result["data"]["active_subscriptions"] == 5
    assert result["data"]["mrr"] == 120.0
    assert result["data"]["arr"] == 1440.0
    assert result["data"]["churn_rate_monthly"] == 40.0
    assert result["data"]["trial_conversion_rate"] == pytest.approx(66.67, rel=1e-2)


@pytest.mark.asyncio
async def test_get_revenue_metrics_returns_breakdown():
    mock_db = AsyncMock()
    service = SubscriptionAnalyticsService(mock_db)

    service._calculate_mrr = AsyncMock(return_value=200.0)
    service._calculate_new_revenue = AsyncMock(return_value=40.0)
    service._calculate_plan_revenue = AsyncMock(
        return_value=[
            {
                "plan_id": str(uuid4()),
                "plan_name": "pro",
                "plan_display_name": "Pro",
                "subscription_count": 12,
                "revenue_monthly": 150.0,
                "revenue_yearly": 1800.0,
            }
        ]
    )

    result = await service.get_revenue_metrics()

    assert result["data"]["current_month"]["mrr"] == 200.0
    assert result["data"]["current_month"]["new_revenue"] == 40.0
    assert result["data"]["growth_rate"] == 20.0
    assert len(result["data"]["by_plan"]) == 1


@pytest.mark.asyncio
async def test_get_churn_analysis_composes_counts():
    mock_db = AsyncMock()
    service = SubscriptionAnalyticsService(mock_db)

    service._count_active_at_start = AsyncMock(return_value=8)
    service._count_new_subscriptions = AsyncMock(return_value=3)
    service._count_cancellations = AsyncMock(return_value=2)
    service._count_active_now = AsyncMock(return_value=9)
    service._get_cancellation_reason_breakdown = AsyncMock(return_value={"too_expensive": 2})

    result = await service.get_churn_analysis(period_days=30)

    assert result["data"]["total_active_start"] == 8
    assert result["data"]["new_subscriptions"] == 3
    assert result["data"]["cancellations"] == 2
    assert result["data"]["churn_rate"] == 25.0
    assert result["data"]["retention_rate"] == 75.0
    assert result["data"]["note"] is None


@pytest.mark.asyncio
async def test_get_churn_analysis_falls_back_when_no_prior_history():
    """When nothing predates the period, churn is measured against in-period subs
    instead of collapsing to 0% churn / 100% retention."""
    mock_db = AsyncMock()
    service = SubscriptionAnalyticsService(mock_db)

    service._count_active_at_start = AsyncMock(return_value=0)
    service._count_new_subscriptions = AsyncMock(return_value=30)
    service._count_cancellations = AsyncMock(return_value=10)
    service._count_active_now = AsyncMock(return_value=17)
    service._get_cancellation_reason_breakdown = AsyncMock(return_value={})

    result = await service.get_churn_analysis(period_days=30)

    assert result["data"]["total_active_start"] == 0
    assert result["data"]["churn_rate"] == pytest.approx(33.33, rel=1e-2)
    assert result["data"]["retention_rate"] == pytest.approx(66.67, rel=1e-2)
    assert result["data"]["note"] is not None


@pytest.mark.asyncio
async def test_get_churn_analysis_retention_never_negative():
    mock_db = AsyncMock()
    service = SubscriptionAnalyticsService(mock_db)

    service._count_active_at_start = AsyncMock(return_value=2)
    service._count_new_subscriptions = AsyncMock(return_value=0)
    service._count_cancellations = AsyncMock(return_value=5)
    service._count_active_now = AsyncMock(return_value=0)
    service._get_cancellation_reason_breakdown = AsyncMock(return_value={})

    result = await service.get_churn_analysis(period_days=30)

    assert result["data"]["retention_rate"] == 0.0


@pytest.mark.asyncio
async def test_get_trial_conversion_metrics_aggregates_values():
    mock_db = AsyncMock()
    service = SubscriptionAnalyticsService(mock_db)

    service._count_trials_started = AsyncMock(return_value=5)
    service._count_trials_converted = AsyncMock(return_value=3)
    service._count_trials_expired = AsyncMock(return_value=1)
    service._count_trials_active = AsyncMock(return_value=1)
    service._average_trial_length = AsyncMock(return_value=12.5)

    result = await service.get_trial_conversion_metrics(period_days=60)

    assert result["data"]["total_trials_started"] == 5
    assert result["data"]["trials_converted"] == 3
    assert result["data"]["trials_expired"] == 1
    assert result["data"]["trials_active"] == 1
    assert result["data"]["conversion_rate"] == 60.0
    assert result["data"]["average_trial_length_days"] == 12.5
