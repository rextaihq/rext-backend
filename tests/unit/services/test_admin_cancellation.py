import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Add src to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from src.api.middleware.exceptions import RextValidationException
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.services.customer_admin_service import CustomerAdminService
from src.services.subscription_service import SubscriptionService


async def test_admin_cancel_success():
    # Mock DB
    db = MagicMock()

    # Mock user and subscription
    user_id = uuid4()
    mock_user = Users(id=user_id, email="test@example.com", status="active")
    mock_sub = UserSubscription(
        id=uuid4(),
        user_id=user_id,
        status=SubscriptionStatus.ACTIVE,
        lemonsqueezy_subscription_id="sub_123",
    )

    # Setup service with mocked dependencies
    admin_service = CustomerAdminService(db)

    # Mock private method for subscription retrieval
    admin_service._get_user = AsyncMock(return_value=mock_user)
    admin_service._get_active_subscription = AsyncMock(return_value=mock_sub)

    # Mock SubscriptionService.cancel
    with patch(
        "src.services.subscription_service.SubscriptionService.cancel", new_callable=AsyncMock
    ) as mock_cancel:
        mock_cancel.return_value = mock_sub
        mock_sub.cancelled_at = datetime.now(timezone.utc)
        mock_sub.cancel_at_period_end = False

        # Mock audit_service.log_admin_action
        with patch(
            "src.services.audit_service.AuditService.log_admin_action", new_callable=AsyncMock
        ) as _mock_audit:
            result = await admin_service.perform_customer_action(
                user_id=user_id,
                action="cancel_subscription",
                reason="Admin request",
                metadata={"cancel_immediately": True},
                admin_user_id=str(uuid4()),
            )

            assert result["status"] == "subscription_cancelled"
            assert mock_cancel.called
            assert mock_cancel.call_args[1]["fail_on_provider_error"] is True
            print("✅ test_admin_cancel_success passed")


async def test_admin_cancel_provider_failure():
    # Mock DB
    db = MagicMock()
    user_id = uuid4()
    mock_user = Users(id=user_id, status="active")
    mock_sub = UserSubscription(id=uuid4(), user_id=user_id, status=SubscriptionStatus.ACTIVE)

    admin_service = CustomerAdminService(db)
    admin_service._get_user = AsyncMock(return_value=mock_user)
    admin_service._get_active_subscription = AsyncMock(return_value=mock_sub)

    # Mock SubscriptionService.cancel to raise exception (simulating provider failure via fail_on_provider_error=True)
    with patch(
        "src.services.subscription_service.SubscriptionService.cancel",
        side_effect=RextValidationException("Provider fail"),
    ):
        try:
            await admin_service.perform_customer_action(
                user_id=user_id,
                action="cancel_subscription",
                reason="Admin request",
                metadata={},
                admin_user_id=str(uuid4()),
            )
            assert False, "Should have raised RextValidationException"
        except RextValidationException as e:
            assert "Provider fail" in str(e)
            print("✅ test_admin_cancel_provider_failure passed")


async def test_subscription_service_fail_flag():
    # Mock DB and Provider
    db = MagicMock()
    user_id = uuid4()
    mock_sub = UserSubscription(
        id=uuid4(),
        user_id=user_id,
        status=SubscriptionStatus.ACTIVE,
        lemonsqueezy_subscription_id="sub_123",
    )

    sub_service = SubscriptionService(db)
    sub_service.get_subscription_by_user = AsyncMock(return_value=mock_sub)

    # Mock provider.cancel_subscription to fail
    sub_service.payment_provider = MagicMock()
    sub_service.payment_provider.cancel_subscription = AsyncMock(side_effect=Exception("API Error"))

    # Test with fail_on_provider_error=True
    try:
        await sub_service.cancel(user_id=user_id, fail_on_provider_error=True)
        assert False, "Should have raised exception"
    except RextValidationException as e:
        assert "Payment provider cancellation failed" in str(e)
        print("✅ test_subscription_service_fail_flag (True) passed")

    # Test with fail_on_provider_error=False (legacy/user path)
    mock_sub.status = SubscriptionStatus.ACTIVE  # reset
    await sub_service.cancel(user_id=user_id, fail_on_provider_error=False)
    # result should not raise, but proceed with local cancel
    print("✅ test_subscription_service_fail_flag (False) passed")


if __name__ == "__main__":

    async def run_tests():
        await test_admin_cancel_success()
        await test_admin_cancel_provider_failure()
        await test_subscription_service_fail_flag()
        print("\nAll Task 374 unit tests passed! 🚀")

    asyncio.run(run_tests())
