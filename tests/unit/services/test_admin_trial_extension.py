import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Add src to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from src.api.middleware.exceptions import RextValidationException
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.services.customer_admin_service import CustomerAdminService


async def test_extend_trial_validation_success():
    # Mock DB
    db = MagicMock()
    user_id = uuid4()
    mock_user = Users(id=user_id, status="active")
    mock_sub = UserSubscription(
        id=uuid4(),
        user_id=user_id,
        status=SubscriptionStatus.TRIAL,
        trial_end_date=datetime.now(timezone.utc),
    )

    admin_service = CustomerAdminService(db)
    admin_service._get_user = AsyncMock(return_value=mock_user)
    admin_service._get_trial_subscription = AsyncMock(return_value=mock_sub)

    # Mock audit_service
    with patch("src.services.audit_service.AuditService.log_admin_action", new_callable=AsyncMock):
        # Valid extension (7 days)
        result = await admin_service.perform_customer_action(
            user_id=user_id,
            action="extend_trial",
            reason="Happy customer",
            metadata={"days": 7},
            admin_user_id=str(uuid4()),
        )

        assert result["status"] == "trial_extended"
        assert result["extension_days"] == 7
        print("✅ test_extend_trial_validation_success passed")


async def test_extend_trial_validation_out_of_range():
    # Mock DB
    db = MagicMock()
    user_id = uuid4()
    mock_user = Users(id=user_id, status="active")
    mock_sub = UserSubscription(id=uuid4(), user_id=user_id, status=SubscriptionStatus.TRIAL)

    admin_service = CustomerAdminService(db)
    admin_service._get_user = AsyncMock(return_value=mock_user)
    admin_service._get_trial_subscription = AsyncMock(return_value=mock_sub)

    # Invalid extension (0 days)
    try:
        await admin_service.perform_customer_action(
            user_id=user_id,
            action="extend_trial",
            reason="Too small",
            metadata={"days": 0},
            admin_user_id=str(uuid4()),
        )
        assert False, "Should have raised RextValidationException for 0 days"
    except RextValidationException as e:
        # Check details for the specific field error
        found = any(
            d["field"] == "metadata.days" and "Must be between 1 and 90" in d["message"]
            for d in e.details
        )
        assert found, f"Validation error detail not found in {e.details}"
        print("✅ test_extend_trial_validation_out_of_range (0) passed")

    # Invalid extension (91 days)
    try:
        await admin_service.perform_customer_action(
            user_id=user_id,
            action="extend_trial",
            reason="Too large",
            metadata={"days": 91},
            admin_user_id=str(uuid4()),
        )
        assert False, "Should have raised RextValidationException for 91 days"
    except RextValidationException as e:
        found = any(
            d["field"] == "metadata.days" and "Must be between 1 and 90" in d["message"]
            for d in e.details
        )
        assert found, f"Validation error detail not found in {e.details}"
        print("✅ test_extend_trial_validation_out_of_range (91) passed")


async def test_extend_trial_validation_wrong_type():
    # Mock DB
    db = MagicMock()
    user_id = uuid4()
    mock_user = Users(id=user_id, status="active")
    mock_sub = UserSubscription(id=uuid4(), user_id=user_id, status=SubscriptionStatus.TRIAL)

    admin_service = CustomerAdminService(db)
    admin_service._get_user = AsyncMock(return_value=mock_user)
    admin_service._get_trial_subscription = AsyncMock(return_value=mock_sub)

    # Invalid extension (string)
    try:
        await admin_service.perform_customer_action(
            user_id=user_id,
            action="extend_trial",
            reason="Malformed",
            metadata={"days": "seven"},
            admin_user_id=str(uuid4()),
        )
        assert False, "Should have raised RextValidationException for string days"
    except RextValidationException as e:
        found = any(
            d["field"] == "metadata.days" and "Must be an integer" in d["message"]
            for d in e.details
        )
        assert found, f"Validation error detail not found in {e.details}"
        print("✅ test_extend_trial_validation_wrong_type passed")


if __name__ == "__main__":

    async def run_tests():
        await test_extend_trial_validation_success()
        await test_extend_trial_validation_out_of_range()
        await test_extend_trial_validation_wrong_type()
        print("\nAll Task 373 unit tests passed! 🚀")

    asyncio.run(run_tests())
