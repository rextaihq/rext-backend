"""
Unit tests for billing plan change emails (upgrades & downgrades).

Tests cover:
- BillingEmailService upgrade and downgrade email methods
- Email preference checks
- Webhook handle_subscription_updated return payloads on upgrade & downgrade
- Webhook route email dispatcher (_send_webhook_email) for plan changes
- Template rendering checks for branding ("Rext AI"), URLs, and pricing display
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from emails.templates.billing import (
    render_subscription_downgraded_email,
    render_subscription_upgraded_email,
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.users import Users
from src.services.billing_email_service import BillingEmailService


class TestPlanChangeTemplates:
    """Test upgrade and downgrade email templates for correct branding and pricing."""

    def test_upgrade_template_branding_and_content(self):
        html = render_subscription_upgraded_email(
            user_name="Alice",
            old_plan_name="Starter Plan",
            new_plan_name="Pro Plan",
            old_price="$29.00/month",
            new_price="$99.00/month",
            billing_date="October 1, 2026",
            dashboard_url="https://app.rext.ai/settings/subscription",
        )
        assert "Alice" in html
        assert "Starter Plan" in html
        assert "Pro Plan" in html
        assert "$29.00/month" in html
        assert "$99.00/month" in html
        assert "October 1, 2026" in html
        assert "Rext AI" in html
        assert "app.rext.com" not in html
        assert "https://app.rext.ai/settings/subscription" in html

    def test_downgrade_template_branding_and_content(self):
        html = render_subscription_downgraded_email(
            user_name="Bob",
            old_plan_name="Pro Plan",
            new_plan_name="Starter Plan",
            old_price="$99.00/month",
            new_price="$29.00/month",
            effective_date="November 1, 2026",
            dashboard_url="https://app.rext.ai/settings/subscription",
        )
        assert "Bob" in html
        assert "Pro Plan" in html
        assert "Starter Plan" in html
        assert "$99.00/month" in html
        assert "$29.00/month" in html
        assert "November 1, 2026" in html
        assert "Rext AI" in html
        assert "app.rext.com" not in html
        assert "https://app.rext.ai/settings/subscription" in html


class TestBillingEmailServicePlanChanges:
    """Test BillingEmailService send_subscription_upgraded_email and send_subscription_downgraded_email."""

    @pytest.mark.asyncio
    @patch.object(BillingEmailService, "_get_user")
    @patch.object(BillingEmailService, "_check_preferences")
    @patch.object(BillingEmailService, "_send_email")
    async def test_send_subscription_upgraded_email_success(
        self, mock_send_email, mock_check_pref, mock_get_user
    ):
        mock_db = AsyncMock()
        service = BillingEmailService(mock_db)

        user_id = uuid4()
        user = Users(
            id=user_id,
            email="test@example.com",
            full_name="Test User",
            status="active",
        )
        mock_get_user.return_value = user
        mock_check_pref.return_value = True
        mock_send_email.return_value = True

        result = await service.send_subscription_upgraded_email(
            user_id=user_id,
            old_plan_name="Starter Plan",
            new_plan_name="Pro Plan",
            old_price="$29.00/month",
            new_price="$99.00/month",
            billing_date="October 1, 2026",
        )

        assert result is True
        mock_check_pref.assert_called_once_with(user_id, "subscription_upgraded")
        mock_send_email.assert_called_once()
        call_kwargs = mock_send_email.call_args.kwargs
        assert call_kwargs["to_email"] == "test@example.com"
        assert "Pro Plan" in call_kwargs["subject"]
        assert "Rext AI" in call_kwargs["subject"]
        assert call_kwargs["template_type"] == "subscription_upgraded"
        assert "Pro Plan" in call_kwargs["html_content"]

    @pytest.mark.asyncio
    @patch.object(BillingEmailService, "_get_user")
    @patch.object(BillingEmailService, "_check_preferences")
    @patch.object(BillingEmailService, "_send_email")
    async def test_send_subscription_downgraded_email_success(
        self, mock_send_email, mock_check_pref, mock_get_user
    ):
        mock_db = AsyncMock()
        service = BillingEmailService(mock_db)

        user_id = uuid4()
        user = Users(
            id=user_id,
            email="test@example.com",
            full_name="Test User",
            status="active",
        )
        mock_get_user.return_value = user
        mock_check_pref.return_value = True
        mock_send_email.return_value = True

        result = await service.send_subscription_downgraded_email(
            user_id=user_id,
            old_plan_name="Pro Plan",
            new_plan_name="Starter Plan",
            old_price="$99.00/month",
            new_price="$29.00/month",
            effective_date="November 1, 2026",
        )

        assert result is True
        mock_check_pref.assert_called_once_with(user_id, "subscription_downgraded")
        mock_send_email.assert_called_once()
        call_kwargs = mock_send_email.call_args.kwargs
        assert call_kwargs["to_email"] == "test@example.com"
        assert "Starter Plan" in call_kwargs["subject"]
        assert "Rext AI" in call_kwargs["subject"]
        assert call_kwargs["template_type"] == "subscription_downgraded"
        assert "Starter Plan" in call_kwargs["html_content"]

    @pytest.mark.asyncio
    @patch.object(BillingEmailService, "_get_user")
    @patch.object(BillingEmailService, "_check_preferences")
    @patch.object(BillingEmailService, "_send_email")
    async def test_send_subscription_upgraded_email_disabled_by_preferences(
        self, mock_send_email, mock_check_pref, mock_get_user
    ):
        mock_db = AsyncMock()
        service = BillingEmailService(mock_db)

        user_id = uuid4()
        user = Users(id=user_id, email="test@example.com", status="active")
        mock_get_user.return_value = user
        mock_check_pref.return_value = False

        result = await service.send_subscription_upgraded_email(
            user_id=user_id,
            old_plan_name="Starter",
            new_plan_name="Pro",
            old_price="$29.00/month",
            new_price="$99.00/month",
            billing_date="October 1, 2026",
        )

        assert result is False
        mock_send_email.assert_not_called()


class TestWebhookPlanChangeEmails:
    """Test webhook subscription update and email task dispatching."""

    @pytest.mark.asyncio
    async def test_handle_subscription_updated_emits_upgrade_email_task(self):
        from src.services.webhook_handlers.subscription_handlers import handle_subscription_updated

        mock_db = AsyncMock()

        user_id = uuid4()
        old_plan_id = uuid4()
        new_plan_id = uuid4()

        old_plan = SubscriptionPlan(
            id=old_plan_id,
            name="starter",
            display_name="Starter Plan",
            price_monthly=29.00,
            price_yearly=290.00,
            lemonsqueezy_variant_id_monthly="var_starter",
        )

        new_plan = SubscriptionPlan(
            id=new_plan_id,
            name="pro",
            display_name="Pro Plan",
            price_monthly=99.00,
            price_yearly=990.00,
            lemonsqueezy_variant_id_monthly="var_pro",
        )

        sub = UserSubscription(
            id=uuid4(),
            user_id=user_id,
            plan_id=old_plan_id,
            lemonsqueezy_subscription_id="ls_sub_123",
            lemonsqueezy_variant_id="var_starter",
            billing_period=BillingPeriod.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
        )

        user = Users(id=user_id, email="subscriber@example.com", status="active")

        # Mock db.execute responses:
        # 1. select UserSubscription
        # 2. select old SubscriptionPlan
        # 3. select new SubscriptionPlan
        # 4. select Users
        result_sub = MagicMock()
        result_sub.scalar_one_or_none.return_value = sub

        result_old_plan = MagicMock()
        result_old_plan.scalar_one_or_none.return_value = old_plan

        result_new_plan = MagicMock()
        result_new_plan.scalar_one_or_none.return_value = new_plan

        result_user = MagicMock()
        result_user.scalar_one_or_none.return_value = user

        mock_db.execute.side_effect = [
            result_sub,
            result_old_plan,
            result_new_plan,
            result_user,
        ]

        webhook_data = {
            "event_id": "evt_123",
            "data": {
                "id": "ls_sub_123",
                "attributes": {
                    "customer_id": "cust_1",
                    "variant_id": "var_pro",
                    "status": "active",
                    "renews_at": "2026-10-01T00:00:00Z",
                    "urls": {"customer_portal": "https://billing.lemonsqueezy.com/portal"},
                },
            },
        }

        mock_event = MagicMock()

        email_task = await handle_subscription_updated(webhook_data, mock_event, mock_db)

        assert email_task is not None
        assert email_task["send_email"] is True
        assert email_task["email_type"] == "subscription_upgraded"
        assert email_task["email_data"]["old_plan_name"] == "Starter Plan"
        assert email_task["email_data"]["new_plan_name"] == "Pro Plan"
        assert "$29.00/month" in email_task["email_data"]["old_price"]
        assert "$99.00/month" in email_task["email_data"]["new_price"]
        assert email_task["email_data"]["customer_portal_url"] == "https://billing.lemonsqueezy.com/portal"

    @pytest.mark.asyncio
    async def test_handle_subscription_updated_emits_downgrade_email_task(self):
        from src.services.webhook_handlers.subscription_handlers import handle_subscription_updated

        mock_db = AsyncMock()

        user_id = uuid4()
        old_plan_id = uuid4()
        new_plan_id = uuid4()

        old_plan = SubscriptionPlan(
            id=old_plan_id,
            name="pro",
            display_name="Pro Plan",
            price_monthly=99.00,
            price_yearly=990.00,
            lemonsqueezy_variant_id_monthly="var_pro",
        )

        new_plan = SubscriptionPlan(
            id=new_plan_id,
            name="starter",
            display_name="Starter Plan",
            price_monthly=29.00,
            price_yearly=290.00,
            lemonsqueezy_variant_id_monthly="var_starter",
        )

        sub = UserSubscription(
            id=uuid4(),
            user_id=user_id,
            plan_id=old_plan_id,
            lemonsqueezy_subscription_id="ls_sub_123",
            lemonsqueezy_variant_id="var_pro",
            billing_period=BillingPeriod.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
        )

        user = Users(id=user_id, email="subscriber@example.com", status="active")

        result_sub = MagicMock()
        result_sub.scalar_one_or_none.return_value = sub

        result_old_plan = MagicMock()
        result_old_plan.scalar_one_or_none.return_value = old_plan

        result_new_plan = MagicMock()
        result_new_plan.scalar_one_or_none.return_value = new_plan

        result_user = MagicMock()
        result_user.scalar_one_or_none.return_value = user

        mock_db.execute.side_effect = [
            result_sub,
            result_old_plan,
            result_new_plan,
            result_user,
        ]

        webhook_data = {
            "event_id": "evt_124",
            "data": {
                "id": "ls_sub_123",
                "attributes": {
                    "customer_id": "cust_1",
                    "variant_id": "var_starter",
                    "status": "active",
                    "renews_at": "2026-11-01T00:00:00Z",
                },
            },
        }

        mock_event = MagicMock()

        email_task = await handle_subscription_updated(webhook_data, mock_event, mock_db)

        assert email_task is not None
        assert email_task["send_email"] is True
        assert email_task["email_type"] == "subscription_downgraded"
        assert email_task["email_data"]["old_plan_name"] == "Pro Plan"
        assert email_task["email_data"]["new_plan_name"] == "Starter Plan"
        assert "$99.00/month" in email_task["email_data"]["old_price"]
        assert "$29.00/month" in email_task["email_data"]["new_price"]

    @pytest.mark.asyncio
    @patch("src.services.billing_email_service.BillingEmailService")
    @patch("src.api.routes.subscriptions.webhook_routes.AsyncSessionLocal")
    async def test_send_webhook_email_dispatches_plan_changes(self, mock_session_local, mock_billing_cls):
        from src.api.routes.subscriptions.webhook_routes import _send_webhook_email

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_billing = AsyncMock()
        mock_billing_cls.return_value = mock_billing

        user_id = uuid4()

        # Test upgrade dispatch
        upgrade_task = {
            "send_email": True,
            "email_type": "subscription_upgraded",
            "email_data": {
                "user_id": str(user_id),
                "old_plan_name": "Starter Plan",
                "new_plan_name": "Pro Plan",
                "old_price": "$29.00/month",
                "new_price": "$99.00/month",
                "billing_date": "October 1, 2026",
                "proration_amount": "$10.00",
                "customer_portal_url": "https://portal.example.com",
            },
        }
        await _send_webhook_email(upgrade_task, None)
        mock_billing.send_subscription_upgraded_email.assert_called_once_with(
            user_id=str(user_id),
            old_plan_name="Starter Plan",
            new_plan_name="Pro Plan",
            old_price="$29.00/month",
            new_price="$99.00/month",
            billing_date="October 1, 2026",
            proration_amount="$10.00",
            customer_portal_url="https://portal.example.com",
        )

        # Test downgrade dispatch
        downgrade_task = {
            "send_email": True,
            "email_type": "subscription_downgraded",
            "email_data": {
                "user_id": str(user_id),
                "old_plan_name": "Pro Plan",
                "new_plan_name": "Starter Plan",
                "old_price": "$99.00/month",
                "new_price": "$29.00/month",
                "effective_date": "November 1, 2026",
                "proration_amount": None,
                "customer_portal_url": "https://portal.example.com",
            },
        }
        await _send_webhook_email(downgrade_task, None)
        mock_billing.send_subscription_downgraded_email.assert_called_once_with(
            user_id=str(user_id),
            old_plan_name="Pro Plan",
            new_plan_name="Starter Plan",
            old_price="$99.00/month",
            new_price="$29.00/month",
            effective_date="November 1, 2026",
            proration_amount=None,
            customer_portal_url="https://portal.example.com",
        )
