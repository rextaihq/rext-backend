"""
Integration test for payment failure webhook handler.

Tests the complete payment failure flow including:
- Grace period calculation and storage
- Status update to SUSPENDED
- Email notification sending
- Database state changes
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from src.services.webhook_handlers.subscription_handlers import handle_subscription_payment_failed
from src.api.models.subscription_models.subscriptions import UserSubscription, SubscriptionStatus, BillingPeriod
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.users import Users
from sqlalchemy import select


@pytest.mark.asyncio
async def test_payment_failure_sets_grace_period(db_session):
    """
    Test that payment failure webhook:
    1. Sets status to SUSPENDED
    2. Calculates and stores 7-day grace period
    3. Tracks payment_failed_at timestamp
    4. Sends email notification
    """
    # Setup: Create test user
    user = Users(
        id=uuid4(),
        email="test@example.com",
        first_name="Test",
        password_hash="hashed",
        is_verified=True
    )
    db_session.add(user)
    await db_session.flush()

    # Setup: Create test plan
    plan = SubscriptionPlan(
        id=uuid4(),
        name="Pro Plan",
        price_monthly=2999,
        price_yearly=29999,
        lemonsqueezy_product_id="123456",
        lemonsqueezy_variant_id_monthly="var_monthly",
        lemonsqueezy_variant_id_yearly="var_yearly",
        max_api_calls_per_month=10000,
        features={"feature1": True}
    )
    db_session.add(plan)
    await db_session.flush()

    # Setup: Create active subscription
    subscription = UserSubscription(
        id=uuid4(),
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        billing_period=BillingPeriod.MONTHLY,
        start_date=datetime.now(timezone.utc) - timedelta(days=30),
        lemonsqueezy_subscription_id="sub_12345",
        lemonsqueezy_customer_id="cus_12345",
        lemonsqueezy_variant_id="var_monthly"
    )
    db_session.add(subscription)
    await db_session.flush()

    # Setup: Create webhook event
    webhook_event = WebhookEvent(
        event_id="evt_payment_failed_123",
        event_name="subscription_payment_failed",
        payload={},
        processed=False
    )
    db_session.add(webhook_event)
    await db_session.flush()

    # Setup: Mock webhook data
    webhook_data = {
        "event_id": "evt_payment_failed_123",
        "event_type": "subscription_payment_failed",
        "data": {
            "type": "subscriptions",
            "id": "sub_12345",
            "attributes": {
                "status": "past_due",
                "customer_id": "cus_12345",
                "variant_id": "var_monthly",
                "first_subscription_item": {
                    "price": 2999,
                    "subscription_id": "sub_12345"
                }
            }
        },
        "meta": {
            "custom_data": {}
        }
    }

    # Record time before webhook processing
    time_before = datetime.now(timezone.utc)

    # Mock email service to prevent actual email sending
    with patch('src.services.webhook_handlers.subscription_handlers.BillingEmailService') as mock_email_service:
        mock_service_instance = AsyncMock()
        mock_service_instance.send_payment_failed_email = AsyncMock(return_value=True)
        mock_email_service.return_value = mock_service_instance

        # Execute: Process webhook
        await handle_subscription_payment_failed(webhook_data, webhook_event, db_session)
        await db_session.commit()

    # Verify: Subscription status updated to SUSPENDED
    await db_session.refresh(subscription)
    assert subscription.status == SubscriptionStatus.SUSPENDED, \
        f"Expected status SUSPENDED, got {subscription.status}"

    # Verify: Grace period set (7 days from now)
    assert subscription.grace_period_end is not None, "Grace period end should be set"
    expected_grace_end = time_before + timedelta(days=7)
    time_diff = abs((subscription.grace_period_end - expected_grace_end).total_seconds())
    assert time_diff < 60, \
        f"Grace period should be ~7 days from now, difference: {time_diff}s"

    # Verify: Payment failed timestamp recorded
    assert subscription.payment_failed_at is not None, "payment_failed_at should be set"
    assert subscription.payment_failed_at >= time_before, \
        "payment_failed_at should be recent"

    # Verify: Email service called
    mock_service_instance.send_payment_failed_email.assert_called_once()
    call_args = mock_service_instance.send_payment_failed_email.call_args
    assert call_args.kwargs['user_id'] == user.id
    assert call_args.kwargs['plan_name'] == "Pro Plan"
    assert call_args.kwargs['amount'] == "$29.99"

    print("✅ Payment failure webhook test passed!")


@pytest.mark.asyncio
async def test_payment_failure_preserves_first_failure_timestamp(db_session):
    """
    Test that payment_failed_at is only set on first failure,
    not overwritten on subsequent failures.
    """
    # Setup user, plan, subscription with existing payment_failed_at
    user = Users(
        id=uuid4(),
        email="test2@example.com",
        first_name="Test",
        password_hash="hashed",
        is_verified=True
    )
    db_session.add(user)

    plan = SubscriptionPlan(
        id=uuid4(),
        name="Pro Plan",
        price_monthly=2999,
        price_yearly=29999,
        lemonsqueezy_product_id="123456",
        lemonsqueezy_variant_id_monthly="var_monthly",
        lemonsqueezy_variant_id_yearly="var_yearly",
        max_api_calls_per_month=10000,
        features={}
    )
    db_session.add(plan)

    # First failure was 2 days ago
    first_failure_time = datetime.now(timezone.utc) - timedelta(days=2)
    subscription = UserSubscription(
        id=uuid4(),
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.SUSPENDED,
        billing_period=BillingPeriod.MONTHLY,
        start_date=datetime.now(timezone.utc) - timedelta(days=30),
        lemonsqueezy_subscription_id="sub_67890",
        lemonsqueezy_customer_id="cus_67890",
        lemonsqueezy_variant_id="var_monthly",
        payment_failed_at=first_failure_time,
        grace_period_end=first_failure_time + timedelta(days=7)
    )
    db_session.add(subscription)
    await db_session.flush()

    webhook_event = WebhookEvent(
        event_id="evt_payment_failed_456",
        event_name="subscription_payment_failed",
        payload={},
        processed=False
    )
    db_session.add(webhook_event)

    webhook_data = {
        "event_id": "evt_payment_failed_456",
        "event_type": "subscription_payment_failed",
        "data": {
            "type": "subscriptions",
            "id": "sub_67890",
            "attributes": {
                "status": "past_due",
                "customer_id": "cus_67890",
                "variant_id": "var_monthly",
                "first_subscription_item": {"price": 2999}
            }
        },
        "meta": {"custom_data": {}}
    }

    # Mock email service
    with patch('src.services.webhook_handlers.subscription_handlers.BillingEmailService') as mock_email:
        mock_instance = AsyncMock()
        mock_instance.send_payment_failed_email = AsyncMock(return_value=True)
        mock_email.return_value = mock_instance

        # Execute: Process second failure
        await handle_subscription_payment_failed(webhook_data, webhook_event, db_session)
        await db_session.commit()

    # Verify: payment_failed_at NOT updated (preserves first failure time)
    await db_session.refresh(subscription)
    assert subscription.payment_failed_at == first_failure_time, \
        "payment_failed_at should preserve the first failure timestamp"

    print("✅ First failure timestamp preservation test passed!")


@pytest.mark.asyncio
async def test_payment_failure_handles_missing_user_gracefully(db_session):
    """
    Test that webhook fails gracefully if user not found.
    """
    # Setup: Plan and subscription but NO user (orphaned subscription)
    plan = SubscriptionPlan(
        id=uuid4(),
        name="Pro Plan",
        price_monthly=2999,
        price_yearly=29999,
        lemonsqueezy_product_id="123456",
        lemonsqueezy_variant_id_monthly="var_monthly",
        lemonsqueezy_variant_id_yearly="var_yearly",
        max_api_calls_per_month=10000,
        features={}
    )
    db_session.add(plan)

    fake_user_id = uuid4()
    subscription = UserSubscription(
        id=uuid4(),
        user_id=fake_user_id,  # User doesn't exist
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        billing_period=BillingPeriod.MONTHLY,
        start_date=datetime.now(timezone.utc),
        lemonsqueezy_subscription_id="sub_orphan",
        lemonsqueezy_customer_id="cus_orphan",
        lemonsqueezy_variant_id="var_monthly"
    )
    db_session.add(subscription)
    await db_session.flush()

    webhook_event = WebhookEvent(
        event_id="evt_orphan",
        event_name="subscription_payment_failed",
        payload={},
        processed=False
    )
    db_session.add(webhook_event)

    webhook_data = {
        "event_id": "evt_orphan",
        "event_type": "subscription_payment_failed",
        "data": {
            "type": "subscriptions",
            "id": "sub_orphan",
            "attributes": {
                "status": "past_due",
                "customer_id": "cus_orphan",
                "variant_id": "var_monthly",
                "first_subscription_item": {"price": 2999}
            }
        },
        "meta": {"custom_data": {}}
    }

    # Execute and verify: Should raise ValueError
    with pytest.raises(ValueError, match="User .* not found"):
        await handle_subscription_payment_failed(webhook_data, webhook_event, db_session)

    print("✅ Missing user error handling test passed!")
