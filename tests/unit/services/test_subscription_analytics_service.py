"""Unit tests for SubscriptionAnalyticsService."""

from unittest.mock import AsyncMock
from uuid import uuid4

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
    service._get_cancellation_reason_breakdown = AsyncMock(return_value={"Too expensive": 2})
    service._calculate_churn_by_plan = AsyncMock(
        return_value=[
            {
                "plan_name": "Pro",
                "churned": 2,
                "total": 11,
                "churn_rate": 18.18,
            }
        ]
    )

    result = await service.get_churn_analysis(period_days=30)

    assert result["data"]["total_active_start"] == 8
    assert result["data"]["new_subscriptions"] == 3
    assert result["data"]["cancellations"] == 2
    # Base = 8 + 3 = 11. Churn = (2 / 11) * 100 = 18.18%
    assert result["data"]["churn_rate"] == 18.18
    assert result["data"]["retention_rate"] == 81.82
    assert result["data"]["cancellation_reasons"] == {"Too expensive": 2}
    assert len(result["data"]["churn_by_plan"]) == 1
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
    service._calculate_churn_by_plan = AsyncMock(return_value=[])

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
    service._calculate_churn_by_plan = AsyncMock(return_value=[])

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
    service._count_trials_cancelled = AsyncMock(return_value=0)
    service._average_trial_length = AsyncMock(return_value=12.5)
    service._calculate_trial_conversion_by_plan = AsyncMock(
        return_value=[
            {
                "plan_name": "Pro",
                "trials": 5,
                "conversions": 3,
                "conversion_rate": 60.0,
            }
        ]
    )

    result = await service.get_trial_conversion_metrics(period_days=60)

    assert result["data"]["total_trials_started"] == 5
    assert result["data"]["trials_converted"] == 3
    assert result["data"]["trials_expired"] == 1
    assert result["data"]["trials_active"] == 1
    assert result["data"]["trials_cancelled"] == 0
    assert result["data"]["conversion_rate"] == 60.0
    assert result["data"]["average_trial_length_days"] == 12.5
    assert len(result["data"]["conversion_by_plan"]) == 1
    assert len(result["data"]["funnel"]) == 5


@pytest.mark.asyncio
async def test_trial_funnel_reconciles_81_started_with_cancelled_cohort():
    """Verify that 81 started = 60 active + 0 converted + 6 expired + 15 cancelled reconciles."""
    mock_db = AsyncMock()
    service = SubscriptionAnalyticsService(mock_db)

    service._count_trials_started = AsyncMock(return_value=81)
    service._count_trials_converted = AsyncMock(return_value=0)
    service._count_trials_expired = AsyncMock(return_value=6)
    service._count_trials_active = AsyncMock(return_value=60)
    service._count_trials_cancelled = AsyncMock(return_value=15)
    service._average_trial_length = AsyncMock(return_value=14.0)
    service._calculate_trial_conversion_by_plan = AsyncMock(return_value=[])

    result = await service.get_trial_conversion_metrics(period_days=30)
    data = result["data"]

    assert data["total_trials_started"] == 81
    assert data["trials_active"] == 60
    assert data["trials_converted"] == 0
    assert data["trials_expired"] == 6
    assert data["trials_cancelled"] == 15

    # Sum of breakdown stages must exactly equal total trials started
    total_breakdown = (
        data["trials_active"]
        + data["trials_converted"]
        + data["trials_expired"]
        + data["trials_cancelled"]
    )
    assert total_breakdown == data["total_trials_started"]
    assert data["conversion_rate"] == 0.0

    # Verify funnel structure
    funnel_map = {item["stage"]: item["count"] for item in data["funnel"]}
    assert funnel_map["Started"] == 81
    assert funnel_map["Active"] == 60
    assert funnel_map["Converted"] == 0
    assert funnel_map["Expired"] == 6
    assert funnel_map["Cancelled"] == 15


@pytest.mark.asyncio
async def test_trial_funnel_auto_reconciles_when_started_underreported():
    """If total_trials_started was undercounted due to missing dates, it reconciles with the sum."""
    mock_db = AsyncMock()
    service = SubscriptionAnalyticsService(mock_db)

    service._count_trials_started = AsyncMock(return_value=70)
    service._count_trials_converted = AsyncMock(return_value=10)
    service._count_trials_expired = AsyncMock(return_value=10)
    service._count_trials_active = AsyncMock(return_value=50)
    service._count_trials_cancelled = AsyncMock(return_value=15)
    service._average_trial_length = AsyncMock(return_value=14.0)
    service._calculate_trial_conversion_by_plan = AsyncMock(return_value=[])

    result = await service.get_trial_conversion_metrics(period_days=30)
    data = result["data"]

    # Reconciles to 50 + 10 + 10 + 15 = 85
    assert data["total_trials_started"] == 85
    assert data["conversion_rate"] == pytest.approx((10 / 85) * 100, rel=1e-2)


def test_parse_cancellation_reasons_pipe_format():
    """Frontend feedback modal saves: 'Reasons: Too expensive, Missing features | Feedback: Too high'"""
    raw = "Reasons: Too expensive, Missing features I need | Feedback: Pricing is too high"
    parsed = SubscriptionAnalyticsService._parse_cancellation_reasons(raw)
    assert parsed == ["Too expensive", "Missing features I need"]


def test_parse_cancellation_reasons_legacy_semicolon():
    """Legacy format: 'Missing features; Additional feedback: need better analytics'"""
    raw = "Missing features; Additional feedback: need better analytics"
    parsed = SubscriptionAnalyticsService._parse_cancellation_reasons(raw)
    assert parsed == ["Missing features"]


def test_parse_cancellation_reasons_plain_and_empty():
    assert SubscriptionAnalyticsService._parse_cancellation_reasons("Account deactivation") == [
        "Account deactivation"
    ]
    assert SubscriptionAnalyticsService._parse_cancellation_reasons("Too expensive") == [
        "Too expensive"
    ]
    assert SubscriptionAnalyticsService._parse_cancellation_reasons("") == []
    assert SubscriptionAnalyticsService._parse_cancellation_reasons("   ") == []
    assert SubscriptionAnalyticsService._parse_cancellation_reasons(None) == []


def test_safe_percentage():
    assert SubscriptionAnalyticsService._safe_percentage(0, 0) == 0.0
    assert SubscriptionAnalyticsService._safe_percentage(10, 0) == 0.0
    assert SubscriptionAnalyticsService._safe_percentage(5, 10) == 50.0
