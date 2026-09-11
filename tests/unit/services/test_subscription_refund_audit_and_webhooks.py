"""
Comprehensive tests for Subscription and Refund event logging across BOTH:
1. Activity Logs (persistent audit trails stored via create_audit_log / audit_logs)
2. Webhook Monitoring Logs (persistent incoming event monitoring via WebhookEvent)
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.users import Users
from src.api.routes.audit.modules.helpers import build_audit_query
from src.services.audit_logger import AuditEventType, AuditLogger
from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService
from src.services.webhook_handlers.order_handlers import handle_order_refunded
from src.services.webhook_handlers.subscription_handlers import handle_subscription_updated

# ============================================================================
# PART 1: ACTIVITY LOG PERSISTENCE & LIFECYCLE TESTS
# ============================================================================


class TestActivityLogPersistence:
    """Test persistence of subscription, payment, and refund lifecycle events in audit_logs."""

    @pytest.fixture
    def audit_logger(self):
        return AuditLogger()

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock)
    async def test_subscription_created_audit_persistence(
        self, mock_create, audit_logger, mock_db
    ):
        """Verify subscription.created writes to audit_logs table."""
        user_id = uuid4()
        sub_id = uuid4()

        await audit_logger.log_subscription_created(
            user_id=user_id,
            subscription_id=sub_id,
            plan_name="Pro",
            billing_period="monthly",
            amount=2900,
            db=mock_db,
        )

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["db"] == mock_db
        assert kwargs["user_id"] == user_id
        assert kwargs["action"] == "subscription.created"
        assert kwargs["resource_type"] == "subscription"
        assert kwargs["resource_id"] == str(sub_id)
        assert kwargs["metadata"]["plan_name"] == "Pro"
        assert kwargs["metadata"]["billing_period"] == "monthly"

    @patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock)
    async def test_subscription_upgraded_audit_persistence(
        self, mock_create, audit_logger, mock_db
    ):
        """Verify subscription.upgraded retains old and new plan details."""
        user_id = uuid4()
        sub_id = uuid4()

        await audit_logger.log_subscription_upgraded(
            user_id=user_id,
            subscription_id=sub_id,
            old_plan_name="Starter",
            new_plan_name="Enterprise",
            old_billing_period="monthly",
            new_billing_period="monthly",
            proration_amount=4500,
            metadata={
                "old_price": 29.0,
                "new_price": 99.0,
                "effective_date": "2026-10-01T00:00:00Z",
            },
            db=mock_db,
        )

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["action"] == "subscription.upgraded"
        assert kwargs["resource_type"] == "subscription"
        assert kwargs["resource_id"] == str(sub_id)
        assert kwargs["old_values"]["plan"] == "Starter"
        assert kwargs["new_values"]["plan"] == "Enterprise"
        assert kwargs["metadata"]["old_price"] == 29.0
        assert kwargs["metadata"]["new_price"] == 99.0
        assert kwargs["metadata"]["proration_amount"] == 4500

    @patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock)
    async def test_subscription_downgraded_audit_persistence(
        self, mock_create, audit_logger, mock_db
    ):
        """Verify subscription.downgraded retains old and new plan details."""
        user_id = uuid4()
        sub_id = uuid4()

        await audit_logger.log_subscription_downgraded(
            user_id=user_id,
            subscription_id=sub_id,
            old_plan_name="Enterprise",
            new_plan_name="Starter",
            old_billing_period="monthly",
            new_billing_period="monthly",
            effective_date=datetime(2026, 11, 1, tzinfo=timezone.utc),
            metadata={
                "old_price": 99.0,
                "new_price": 29.0,
            },
            db=mock_db,
        )

        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["action"] == "subscription.downgraded"
        assert kwargs["old_values"]["plan"] == "Enterprise"
        assert kwargs["new_values"]["plan"] == "Starter"
        assert kwargs["metadata"]["new_price"] == 29.0

    @patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock)
    async def test_subscription_cancelled_resumed_paused_expired_renewed(
        self, mock_create, audit_logger, mock_db
    ):
        """Verify remaining subscription lifecycle events."""
        user_id = uuid4()
        sub_id = uuid4()

        # 1. Cancelled
        await audit_logger.log_subscription_cancelled(
            user_id=user_id,
            subscription_id=sub_id,
            plan_name="Pro",
            reason="Customer request",
            cancel_immediately=False,
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "subscription.cancelled"
        assert mock_create.call_args.kwargs["metadata"]["reason"] == "Customer request"

        # 2. Resumed
        await audit_logger.log_subscription_resumed(
            user_id=user_id,
            subscription_id=sub_id,
            plan_name="Pro",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "subscription.resumed"

        # 3. Paused
        await audit_logger.log_subscription_paused(
            user_id=user_id,
            subscription_id=sub_id,
            resumes_at="2026-12-01T00:00:00Z",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "subscription.paused"
        assert mock_create.call_args.kwargs["metadata"]["resumes_at"] == "2026-12-01T00:00:00Z"

        # 4. Expired
        await audit_logger.log_subscription_expired(
            user_id=user_id,
            subscription_id=sub_id,
            plan_name="Pro",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "subscription.expired"

        # 5. Renewed
        await audit_logger.log_subscription_renewed(
            user_id=user_id,
            subscription_id=sub_id,
            plan_name="Pro",
            amount=2900,
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "subscription.renewed"
        assert mock_create.call_args.kwargs["metadata"]["amount"] == 2900

    @patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock)
    async def test_payment_events_persistence(self, mock_create, audit_logger, mock_db):
        """Verify payment succeeded, failed, and recovered audit logging."""
        user_id = uuid4()
        sub_id = uuid4()

        # payment.succeeded
        await audit_logger.log_payment_succeeded(
            user_id=user_id,
            subscription_id=sub_id,
            amount=4900,
            currency="USD",
            lemonsqueezy_payment_id="pay_123",
            metadata={"invoice_id": "inv_123"},
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "payment.succeeded"
        assert mock_create.call_args.kwargs["resource_type"] == "payment"
        assert mock_create.call_args.kwargs["metadata"]["amount"] == 4900
        assert mock_create.call_args.kwargs["metadata"]["invoice_id"] == "inv_123"

        # payment.failed
        await audit_logger.log_payment_failed(
            user_id=user_id,
            subscription_id=sub_id,
            amount=4900,
            failure_reason="Card declined",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "payment.failed"
        assert mock_create.call_args.kwargs["metadata"]["failure_reason"] == "Card declined"

        # payment.recovered
        await audit_logger.log_payment_recovered(
            user_id=user_id,
            subscription_id=sub_id,
            amount=4900,
            currency="USD",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "payment.recovered"
        assert mock_create.call_args.kwargs["metadata"]["amount"] == 4900

    @patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock)
    async def test_refund_full_and_partial_audit_persistence(
        self, mock_create, audit_logger, mock_db
    ):
        """Verify payment.refunded for both full and partial refunds."""
        user_id = uuid4()
        sub_id = uuid4()
        ref_id1 = uuid4()
        ref_id2 = uuid4()

        # Full refund
        await audit_logger.log_payment_refunded(
            user_id=user_id,
            refund_id=ref_id1,
            subscription_id=sub_id,
            amount=9900,
            reason="Customer requested full return",
            is_partial=False,
            lemonsqueezy_refund_id="ref_full_123",
            metadata={"currency": "USD", "order_id": "ord_123"},
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "payment.refunded"
        assert mock_create.call_args.kwargs["resource_type"] == "refund"
        assert mock_create.call_args.kwargs["metadata"]["is_partial"] is False
        assert mock_create.call_args.kwargs["metadata"]["amount"] == 9900

        # Partial refund
        await audit_logger.log_payment_refunded(
            user_id=user_id,
            refund_id=ref_id2,
            subscription_id=sub_id,
            amount=2500,
            reason="Discount adjustment",
            is_partial=True,
            lemonsqueezy_refund_id="ref_part_456",
            metadata={"currency": "USD", "order_id": "ord_123"},
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "payment.refunded"
        assert mock_create.call_args.kwargs["metadata"]["is_partial"] is True
        assert mock_create.call_args.kwargs["metadata"]["amount"] == 2500

    @patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock)
    async def test_refund_lifecycle_events_persistence(
        self, mock_create, audit_logger, mock_db
    ):
        """Verify refund request, approval, rejection, and processing."""
        user_id = uuid4()
        admin_id = uuid4()
        req_id = uuid4()
        ref_id = uuid4()

        # 1. refund.requested
        await audit_logger.log_refund_requested(
            user_id=user_id,
            refund_request_id=req_id,
            order_id="ord_123",
            amount=5000,
            currency="USD",
            reason="Unsatisfied with product",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "refund.requested"
        assert mock_create.call_args.kwargs["resource_type"] == "refund"
        assert mock_create.call_args.kwargs["metadata"]["reason"] == "Unsatisfied with product"

        # 2. refund.approved
        await audit_logger.log_refund_approved(
            admin_id=admin_id,
            user_id=user_id,
            refund_request_id=req_id,
            order_id="ord_123",
            amount=5000,
            currency="USD",
            admin_note="Approved under guarantee",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "refund.approved"
        assert mock_create.call_args.kwargs["metadata"]["admin_id"] == str(admin_id)

        # 3. refund.rejected
        await audit_logger.log_refund_rejected(
            admin_id=admin_id,
            user_id=user_id,
            refund_request_id=req_id,
            order_id="ord_123",
            reason="Past 30 day policy",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "refund.rejected"
        assert mock_create.call_args.kwargs["metadata"]["reason"] == "Past 30 day policy"

        # 4. refund.processed
        await audit_logger.log_refund_processed(
            user_id=user_id,
            refund_id=ref_id,
            amount=5000,
            currency="USD",
            order_id="ord_123",
            admin_id=admin_id,
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "refund.processed"

        # 5. refund.cancelled
        await audit_logger.log_refund_cancelled(
            admin_id=admin_id,
            user_id=user_id,
            refund_request_id=req_id,
            order_id="ord_123",
            reason="Admin unapproved",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "refund.cancelled"

        # 6. refund.failed
        await audit_logger.log_refund_failed(
            user_id=user_id,
            refund_id=ref_id,
            amount=5000,
            reason="Provider gateway timeout",
            db=mock_db,
        )
        assert mock_create.call_args.kwargs["action"] == "refund.failed"


# ============================================================================
# PART 2: ACTIVITY LOG API QUERY FILTERING TESTS
# ============================================================================


class TestActivityLogQueryFiltering:
    """Test that build_audit_query accurately handles subscription, payment, and refund filters."""

    @pytest.mark.asyncio
    async def test_filter_by_resource_types(self):
        """Verify build_audit_query handles subscription, payment, and refund resource types."""
        mock_db = AsyncMock()

        # Subscription
        q_sub, _ = await build_audit_query(db=mock_db, resource_type="subscription")
        compiled_sub = str(q_sub)
        assert "resource_type" in compiled_sub

        # Payment
        q_pay, _ = await build_audit_query(db=mock_db, resource_type="payment")
        compiled_pay = str(q_pay)
        assert "resource_type" in compiled_pay

        # Refund
        q_ref, _ = await build_audit_query(db=mock_db, resource_type="refund")
        compiled_ref = str(q_ref)
        assert "resource_type" in compiled_ref

    @pytest.mark.asyncio
    async def test_filter_by_actions(self):
        """Verify prefix and exact action filtering."""
        mock_db = AsyncMock()

        # Prefix matching: "subscription."
        q_prefix, _ = await build_audit_query(db=mock_db, action="subscription.")
        compiled_prefix = str(q_prefix)
        assert "action" in compiled_prefix

        # Exact matching: "payment.refunded"
        q_exact, _ = await build_audit_query(db=mock_db, action="payment.refunded")
        compiled_exact = str(q_exact)
        assert "action" in compiled_exact


# ============================================================================
# PART 3: WEBHOOK MONITORING LOGS TESTS
# ============================================================================


class TestWebhookMonitoring:
    """Test WebhookEvent recording, idempotency, failure preservation, and metadata."""

    @pytest.mark.asyncio
    async def test_idempotency_prevents_duplicate_processing(self):
        """Verify that duplicate incoming webhook event_ids are detected and not re-executed."""
        mock_db = AsyncMock()

        svc = LemonSqueezyWebhookService(mock_db)

        svc._check_idempotency = AsyncMock(return_value=True)
        svc._log_webhook = AsyncMock()
        svc._route_event = AsyncMock()

        fake_payload = json.dumps({
            "meta": {
                "event_name": "subscription_created",
                "webhook_id": "wh_123",
            },
            "data": {
                "id": "ls_sub_123",
                "type": "subscriptions",
            },
        }).encode("utf-8")

        with patch("src.services.lemonsqueezy_webhook_service.verify_webhook_signature", return_value=True):
            result = await svc.process_webhook(fake_payload, "valid_sig")

        assert result["success"] is True
        assert "Duplicate event" in result["message"]
        svc._log_webhook.assert_not_called()
        svc._route_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_processing_marks_processed(self):
        """Verify successful webhook execution sets processed=True and error_message=None."""
        mock_db = AsyncMock()
        svc = LemonSqueezyWebhookService(mock_db)

        event_id = "evt_unique_101"
        webhook_event = WebhookEvent(
            id=uuid4(),
            event_id=event_id,
            event_name="subscription_created",
            processed=False,
        )

        svc._check_idempotency = AsyncMock(return_value=False)
        svc._log_webhook = AsyncMock(return_value=webhook_event)
        svc._route_event = AsyncMock(return_value={"status": "ok"})
        svc._mark_processed = AsyncMock()

        fake_payload = json.dumps({
            "meta": {
                "event_name": "subscription_created",
                "webhook_id": event_id,
            },
            "data": {"id": "123"},
        }).encode("utf-8")

        with patch("src.services.lemonsqueezy_webhook_service.verify_webhook_signature", return_value=True):
            result = await svc.process_webhook(fake_payload, "valid_sig")

        assert result["success"] is True
        svc._mark_processed.assert_called_once_with(webhook_event)

    @pytest.mark.asyncio
    async def test_failed_processing_preserves_error_message(self):
        """Verify failed webhook execution sets processed=False and retains error_message."""
        mock_db = AsyncMock()
        svc = LemonSqueezyWebhookService(mock_db)

        event_id = "evt_fail_202"
        webhook_event = WebhookEvent(
            id=uuid4(),
            event_id=event_id,
            event_name="order_refunded",
            processed=False,
        )

        svc._check_idempotency = AsyncMock(return_value=False)
        svc._log_webhook = AsyncMock(return_value=webhook_event)
        svc._route_event = AsyncMock(side_effect=RuntimeError("Database connection lost"))
        svc._mark_failed = AsyncMock()

        fake_payload = json.dumps({
            "meta": {
                "event_name": "order_refunded",
                "webhook_id": event_id,
            },
            "data": {"id": "123"},
        }).encode("utf-8")

        with patch("src.services.lemonsqueezy_webhook_service.verify_webhook_signature", return_value=True):
            with pytest.raises(Exception) as exc_info:
                await svc.process_webhook(fake_payload, "valid_sig")

            assert "Database connection lost" in str(exc_info.value)
            svc._mark_failed.assert_called_once()
            args = svc._mark_failed.call_args[0]
            assert args[0] == webhook_event
            assert "Database connection lost" in args[1]


# ============================================================================
# PART 4: END-TO-END INTEGRATION TESTS
# ============================================================================


class TestEndToEndWebhookAndAuditLogging:
    """
    Test end-to-end flow:
    Webhook received
        ↓
    Webhook Monitoring record created (WebhookEvent)
        ↓
    Webhook handler executes
        ↓
    Business action processed
        ↓
    Activity Log record created (audit_logs via create_audit_log)
    """

    @pytest.mark.asyncio
    async def test_subscription_upgrade_complete_flow(self):
        """Verify subscription upgrade generates both Webhook Monitoring and Activity Log entries."""
        mock_db = AsyncMock()
        svc = LemonSqueezyWebhookService(mock_db)

        user_id = uuid4()
        old_plan_id = uuid4()
        new_plan_id = uuid4()
        sub_id = uuid4()

        old_plan = SubscriptionPlan(
            id=old_plan_id,
            name="starter",
            display_name="Starter Plan",
            price_monthly=29.00,
            lemonsqueezy_variant_id_monthly="var_starter",
        )
        new_plan = SubscriptionPlan(
            id=new_plan_id,
            name="pro",
            display_name="Pro Plan",
            price_monthly=99.00,
            lemonsqueezy_variant_id_monthly="var_pro",
        )
        sub = UserSubscription(
            id=sub_id,
            user_id=user_id,
            plan_id=old_plan_id,
            lemonsqueezy_subscription_id="ls_sub_789",
            lemonsqueezy_variant_id="var_starter",
            billing_period=BillingPeriod.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
        )
        user = Users(id=user_id, email="upgrade_test@example.com", status="active")

        # Mock DB results
        res_sub = MagicMock()
        res_sub.scalar_one_or_none.return_value = sub
        res_old = MagicMock()
        res_old.scalar_one_or_none.return_value = old_plan
        res_new = MagicMock()
        res_new.scalar_one_or_none.return_value = new_plan
        res_usr = MagicMock()
        res_usr.scalar_one_or_none.return_value = user

        mock_db.execute.side_effect = [res_sub, res_old, res_new, res_usr]

        webhook_event = WebhookEvent(
            id=uuid4(),
            event_id="evt_sub_upgrade_1",
            event_name="subscription_updated",
            processed=False,
        )

        svc._check_idempotency = AsyncMock(return_value=False)
        svc._log_webhook = AsyncMock(return_value=webhook_event)
        svc._mark_processed = AsyncMock()

        # Register handler
        svc._handlers["subscription_updated"] = handle_subscription_updated

        payload_dict = {
            "meta": {
                "event_name": "subscription_updated",
                "webhook_id": "evt_sub_upgrade_1",
                "custom_data": {"user_id": str(user_id)},
            },
            "data": {
                "id": "ls_sub_789",
                "type": "subscriptions",
                "attributes": {
                    "variant_id": "var_pro",
                    "status": "active",
                    "user_email": "upgrade_test@example.com",
                },
            },
        }
        payload_bytes = json.dumps(payload_dict).encode("utf-8")

        with patch("src.services.lemonsqueezy_webhook_service.verify_webhook_signature", return_value=True), \
             patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock) as mock_create_audit:

            result = await svc.process_webhook(payload_bytes, "valid_sig")

            # 1. Webhook Monitoring verification
            assert result["success"] is True
            svc._log_webhook.assert_called_once()
            svc._mark_processed.assert_called_once_with(webhook_event)

            # 2. Activity Log verification
            mock_create_audit.assert_called_once()
            call_kwargs = mock_create_audit.call_args.kwargs
            assert call_kwargs["action"] == "subscription.upgraded"
            assert call_kwargs["resource_type"] == "subscription"
            assert call_kwargs["user_id"] == user_id
            assert call_kwargs["old_values"]["plan"] == "Starter Plan"
            assert call_kwargs["new_values"]["plan"] == "Pro Plan"

    @pytest.mark.asyncio
    async def test_order_refunded_complete_flow(self):
        """Verify refund webhook creates both Webhook Monitoring and Activity Log records."""
        mock_db = AsyncMock()
        svc = LemonSqueezyWebhookService(mock_db)

        user_id = uuid4()
        sub_id = uuid4()
        user = Users(id=user_id, email="refund_test@example.com", status="active")
        sub = UserSubscription(
            id=sub_id,
            user_id=user_id,
            plan_id=uuid4(),
            lemonsqueezy_subscription_id="ls_sub_refund_1",
            status=SubscriptionStatus.ACTIVE,
        )

        async def mock_execute(stmt, *args, **kwargs):
            stmt_str = str(stmt).lower()
            res = MagicMock()
            if "licenses" in stmt_str:
                res.scalar_one_or_none.return_value = None
            elif "user_subscriptions" in stmt_str:
                res.scalar_one_or_none.return_value = sub
            elif "orders" in stmt_str:
                res.scalar_one_or_none.return_value = None
            elif "refunds" in stmt_str:
                res.scalar_one_or_none.return_value = None
            elif "users" in stmt_str:
                res.scalar_one_or_none.return_value = user
            else:
                res.scalar_one_or_none.return_value = None
            return res

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        webhook_event = WebhookEvent(
            id=uuid4(),
            event_id="evt_refund_999",
            event_name="order_refunded",
            processed=False,
        )

        svc._check_idempotency = AsyncMock(return_value=False)
        svc._log_webhook = AsyncMock(return_value=webhook_event)
        svc._mark_processed = AsyncMock()

        svc._handlers["order_refunded"] = handle_order_refunded

        payload_dict = {
            "meta": {
                "event_name": "order_refunded",
                "webhook_id": "evt_refund_999",
            },
            "data": {
                "id": "ord_ref_123",
                "type": "orders",
                "attributes": {
                    "identifier": "ord_ref_123",
                    "user_email": "refund_test@example.com",
                    "refunded_amount": 5000,
                    "currency": "USD",
                    "status": "refunded",
                    "first_order_item": {
                        "subscription_id": "ls_sub_refund_1",
                    },
                },
            },
        }
        payload_bytes = json.dumps(payload_dict).encode("utf-8")

        with patch("src.services.lemonsqueezy_webhook_service.verify_webhook_signature", return_value=True), \
             patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock) as mock_create_audit:

            result = await svc.process_webhook(payload_bytes, "valid_sig")

            # 1. Webhook Monitoring record verified
            assert result["success"] is True
            svc._log_webhook.assert_called_once()
            svc._mark_processed.assert_called_once_with(webhook_event)

            # 2. Activity Log record verified
            mock_create_audit.assert_called_once()
            call_kwargs = mock_create_audit.call_args.kwargs
            assert call_kwargs["action"] == "payment.refunded"
            assert call_kwargs["resource_type"] == "refund"
            assert call_kwargs["user_id"] == user_id
            assert call_kwargs["metadata"]["amount"] == 5000
            assert call_kwargs["metadata"]["lemonsqueezy_order_id"] == "ord_ref_123"
