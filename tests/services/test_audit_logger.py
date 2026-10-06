"""
Tests for audit logging service.

Tests comprehensive audit logging for all payment, subscription, webhook,
and administrative operations.
"""

import logging
from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.services.audit_logger import AuditEventType, AuditLogger


@pytest.fixture
def audit_logger():
    """Create audit logger instance for testing."""
    return AuditLogger()


@pytest.fixture
def capture_logs(caplog):
    """Capture audit logs for verification."""
    caplog.set_level(logging.INFO, logger="audit")
    return caplog


class TestAuditLogger:
    """Test suite for AuditLogger class."""

    def test_initialization(self, audit_logger):
        """Test audit logger initialization."""
        assert audit_logger is not None
        assert audit_logger.logger.name == "audit"

    async def test_log_subscription_created(self, audit_logger, capture_logs):
        """Test subscription creation audit log."""
        user_id = uuid4()
        subscription_id = uuid4()
        plan_id = uuid4()

        await audit_logger.log_subscription_created(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_id=plan_id,
            plan_name="Pro",
            billing_period="monthly",
            is_trial=False,
            amount=1999,
            lemonsqueezy_subscription_id="sub_123",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert log_record.levelname == "INFO"
        assert "subscription.created" in log_record.message
        assert "audit" in log_record.__dict__

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "subscription.created"
        assert audit_data["user_id"] == str(user_id)
        assert audit_data["resource_type"] == "subscription"
        assert audit_data["resource_id"] == str(subscription_id)
        assert audit_data["metadata"]["plan_name"] == "Pro"
        assert audit_data["metadata"]["billing_period"] == "monthly"
        assert audit_data["metadata"]["amount"] == 1999

    async def test_log_subscription_cancelled(self, audit_logger, capture_logs):
        """Test subscription cancellation audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_cancelled(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_name="Pro",
            reason="Too expensive",
            cancel_immediately=True,
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "subscription.cancelled" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "subscription.cancelled"
        assert audit_data["metadata"]["reason"] == "Too expensive"
        assert audit_data["metadata"]["cancel_immediately"] is True

    async def test_log_subscription_upgraded(self, audit_logger, capture_logs):
        """Test subscription upgrade audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_upgraded(
            user_id=user_id,
            subscription_id=subscription_id,
            old_plan_name="Basic",
            new_plan_name="Pro",
            old_billing_period="monthly",
            new_billing_period="yearly",
            proration_amount=500,
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "subscription.upgraded" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["changes"]["plan"]["from"] == "Basic"
        assert audit_data["changes"]["plan"]["to"] == "Pro"
        assert audit_data["metadata"]["proration_amount"] == 500

    async def test_log_subscription_downgraded(self, audit_logger, capture_logs):
        """Test subscription downgrade audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_downgraded(
            user_id=user_id,
            subscription_id=subscription_id,
            old_plan_name="Pro",
            new_plan_name="Basic",
            old_billing_period="yearly",
            new_billing_period="monthly",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "subscription.downgraded" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "subscription.downgraded"
        assert audit_data["changes"]["plan"]["from"] == "Pro"
        assert audit_data["changes"]["plan"]["to"] == "Basic"

    async def test_log_subscription_resumed(self, audit_logger, capture_logs):
        """Test subscription resumed audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_resumed(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_name="Pro",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "subscription.resumed" in log_record.message
        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "subscription.resumed"

    async def test_log_subscription_paused(self, audit_logger, capture_logs):
        """Test subscription paused audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_paused(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_name="Pro",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "subscription.paused" in log_record.message
        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "subscription.paused"

    async def test_log_subscription_expired(self, audit_logger, capture_logs):
        """Test subscription expired audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_expired(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_name="Pro",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "subscription.expired" in log_record.message
        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "subscription.expired"

    async def test_log_payment_succeeded(self, audit_logger, capture_logs):
        """Test successful payment audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_payment_succeeded(
            user_id=user_id,
            subscription_id=subscription_id,
            amount=1999,
            currency="USD",
            lemonsqueezy_payment_id="pay_123",
            card_brand="Visa",
            card_last_four="4242",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "payment.succeeded" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "payment.succeeded"
        assert audit_data["metadata"]["amount"] == 1999
        assert audit_data["metadata"]["card_brand"] == "Visa"
        assert audit_data["metadata"]["card_last_four"] == "4242"

    async def test_log_payment_failed(self, audit_logger, capture_logs):
        """Test failed payment audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_payment_failed(
            user_id=user_id,
            subscription_id=subscription_id,
            amount=1999,
            failure_reason="Insufficient funds",
            lemonsqueezy_payment_id="pay_456",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "payment.failed" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "payment.failed"
        assert audit_data["metadata"]["failure_reason"] == "Insufficient funds"

    async def test_log_payment_recovered(self, audit_logger, capture_logs):
        """Test payment recovered audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_payment_recovered(
            user_id=user_id,
            subscription_id=subscription_id,
            amount=1999,
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "payment.recovered" in log_record.message
        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "payment.recovered"

    async def test_log_payment_refunded(self, audit_logger, capture_logs):
        """Test payment refund audit log."""
        user_id = uuid4()
        refund_id = uuid4()
        subscription_id = uuid4()
        admin_id = uuid4()

        await audit_logger.log_payment_refunded(
            user_id=user_id,
            refund_id=refund_id,
            subscription_id=subscription_id,
            amount=1999,
            reason="Customer request",
            is_partial=False,
            admin_id=admin_id,
            lemonsqueezy_refund_id="ref_789",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "payment.refunded" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "payment.refunded"
        assert audit_data["admin_id"] == str(admin_id)
        assert audit_data["metadata"]["reason"] == "Customer request"
        assert audit_data["metadata"]["is_partial"] is False

    async def test_log_refund_lifecycle(self, audit_logger, capture_logs):
        """Test refund requested, approved, rejected, cancelled, and failed logs."""
        user_id = uuid4()
        request_id = uuid4()
        admin_id = uuid4()
        refund_id = uuid4()

        # Requested
        await audit_logger.log_refund_requested(
            user_id=user_id,
            refund_request_id=request_id,
            order_id="ord_123",
            amount=50.0,
            currency="USD",
            reason="Mistake",
        )
        assert any("refund.requested" in r.message for r in capture_logs.records)

        # Approved
        await audit_logger.log_refund_approved(
            admin_id=admin_id,
            user_id=user_id,
            refund_request_id=request_id,
            order_id="ord_123",
            amount=5000,
        )
        assert any("refund.approved" in r.message for r in capture_logs.records)

        # Rejected
        await audit_logger.log_refund_rejected(
            admin_id=admin_id,
            user_id=user_id,
            refund_request_id=request_id,
            order_id="ord_123",
            reason="Outside 14 day window",
        )
        assert any("refund.rejected" in r.message for r in capture_logs.records)

        # Cancelled
        await audit_logger.log_refund_cancelled(
            admin_id=admin_id,
            user_id=user_id,
            refund_request_id=request_id,
            order_id="ord_123",
            reason="User cancelled",
        )
        assert any("refund.cancelled" in r.message for r in capture_logs.records)

        # Failed
        await audit_logger.log_refund_failed(
            user_id=user_id,
            refund_id=refund_id,
            amount=5000,
            reason="Provider declined",
        )
        assert any("refund.failed" in r.message for r in capture_logs.records)

    async def test_log_checkout_created(self, audit_logger, capture_logs):
        """Test checkout creation audit log."""
        user_id = uuid4()
        plan_id = uuid4()

        await audit_logger.log_checkout_created(
            user_id=user_id,
            plan_id=plan_id,
            plan_name="Pro",
            billing_period="monthly",
            checkout_url="https://checkout.lemonsqueezy.com/abc123",
            discount_code="SAVE20",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "checkout.created" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "checkout.created"
        assert audit_data["metadata"]["discount_code"] == "SAVE20"

    async def test_log_webhook_received(self, audit_logger, capture_logs):
        """Test webhook received audit log."""
        await audit_logger.log_webhook_received(
            event_id="evt_123",
            event_name="subscription_created",
            signature_valid=True,
            ip_address="203.0.113.45",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "webhook.received" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "webhook.received"
        assert audit_data["metadata"]["signature_valid"] is True
        assert audit_data["ip_address"] == "203.0.113.45"

    async def test_log_webhook_processed(self, audit_logger, capture_logs):
        """Test webhook processed audit log."""
        user_id = uuid4()

        await audit_logger.log_webhook_processed(
            event_id="evt_123",
            event_name="subscription_created",
            processing_time_ms=145.3,
            user_id=user_id,
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "webhook.processed" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "webhook.processed"
        assert audit_data["metadata"]["processing_time_ms"] == 145.3

    async def test_log_webhook_failed(self, audit_logger, capture_logs):
        """Test webhook failed audit log."""
        await audit_logger.log_webhook_failed(
            event_id="evt_456",
            event_name="subscription_updated",
            error="Subscription not found",
            retry_count=2,
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "webhook.failed" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "webhook.failed"
        assert audit_data["metadata"]["error"] == "Subscription not found"
        assert audit_data["metadata"]["retry_count"] == 2

    async def test_log_admin_refund_created(self, audit_logger, capture_logs):
        """Test admin refund creation audit log."""
        admin_id = uuid4()
        user_id = uuid4()
        refund_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_admin_refund_created(
            admin_id=admin_id,
            user_id=user_id,
            refund_id=refund_id,
            subscription_id=subscription_id,
            amount=1999,
            reason="Duplicate charge",
            ip_address="192.0.2.100",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "admin.refund_created" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "admin.refund_created"
        assert audit_data["admin_id"] == str(admin_id)
        assert audit_data["metadata"]["reason"] == "Duplicate charge"
        assert audit_data["ip_address"] == "192.0.2.100"

    async def test_log_admin_subscription_extended(self, audit_logger, capture_logs):
        """Test admin subscription extended audit log."""
        admin_id = uuid4()
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_admin_subscription_extended(
            admin_id=admin_id,
            user_id=user_id,
            subscription_id=subscription_id,
            extend_days=30,
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "admin.subscription_extended" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "admin.subscription_extended"
        assert audit_data["admin_id"] == str(admin_id)
        assert audit_data["metadata"]["extend_days"] == 30

    async def test_log_admin_subscription_cancelled(self, audit_logger, capture_logs):
        """Test admin subscription cancellation audit log."""
        admin_id = uuid4()
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_admin_subscription_cancelled(
            admin_id=admin_id,
            user_id=user_id,
            subscription_id=subscription_id,
            reason="Terms violation",
            cancel_immediately=True,
            ip_address="192.0.2.101",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "admin.subscription_cancelled" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "admin.subscription_cancelled"
        assert audit_data["admin_id"] == str(admin_id)
        assert audit_data["metadata"]["reason"] == "Terms violation"
        assert audit_data["metadata"]["cancel_immediately"] is True

    async def test_log_trial_started(self, audit_logger, capture_logs):
        """Test trial start audit log."""
        user_id = uuid4()
        subscription_id = uuid4()
        trial_end_date = datetime(2025, 11, 1)

        await audit_logger.log_trial_started(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_name="Pro",
            trial_days=14,
            trial_end_date=trial_end_date,
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "trial.started" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "trial.started"
        assert audit_data["metadata"]["trial_days"] == 14
        assert "2025-11-01" in audit_data["metadata"]["trial_end_date"]

    async def test_log_trial_converted(self, audit_logger, capture_logs):
        """Test trial conversion audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_trial_converted(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_name="Pro",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "trial.converted" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "trial.converted"
        assert audit_data["metadata"]["plan_name"] == "Pro"

    async def test_structured_logging_format(self, audit_logger, capture_logs):
        """Test that audit logs use structured JSON format."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_created(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_id=uuid4(),
            plan_name="Pro",
            billing_period="monthly",
        )

        log_record = capture_logs.records[0]
        audit_data = log_record.__dict__["audit"]

        # Verify all standard fields are present
        assert "event_type" in audit_data
        assert "timestamp" in audit_data
        assert "user_id" in audit_data
        assert "resource_type" in audit_data
        assert "resource_id" in audit_data
        assert "metadata" in audit_data

        # Verify timestamp is ISO format
        timestamp = audit_data["timestamp"]
        datetime.fromisoformat(timestamp)  # Should not raise exception

    async def test_structured_payload_is_embedded_in_message(self, audit_logger, capture_logs):
        """
        The root log handler is configured with ``format="%(message)s"``, so
        anything passed only via ``extra=`` is dropped from the actual output.
        The full audit payload must therefore live in the message string itself.
        """
        import json

        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_created(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_id=uuid4(),
            plan_name="Pro",
            billing_period="monthly",
            amount=2999,
            lemonsqueezy_subscription_id="ls_sub_123",
        )

        message = capture_logs.records[0].getMessage()
        assert str(user_id) in message
        assert str(subscription_id) in message
        assert "Pro" in message
        assert "2999" in message
        assert "ls_sub_123" in message

        json_part = message[message.index("{") :]
        parsed = json.loads(json_part)
        assert parsed["event_type"] == "subscription.created"
        assert parsed["metadata"]["plan_name"] == "Pro"

    async def test_none_values_excluded(self, audit_logger, capture_logs):
        """Test that None values are excluded from audit logs."""
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_cancelled(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_name="Pro",
        )

        log_record = capture_logs.records[0]
        audit_data = log_record.__dict__["audit"]

        assert "admin_id" not in audit_data
        assert "ip_address" not in audit_data
        assert "user_id" in audit_data
        assert "event_type" in audit_data

    @patch("src.utils.audit_helper.create_audit_log", new_callable=AsyncMock)
    async def test_database_persistence_called_when_db_provided(
        self, mock_create_audit_log, audit_logger, capture_logs
    ):
        """Verify that when db is provided, create_audit_log is invoked to persist to audit_logs table."""
        mock_db = AsyncMock()
        user_id = uuid4()
        subscription_id = uuid4()

        await audit_logger.log_subscription_created(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_name="Pro",
            billing_period="monthly",
            db=mock_db,
        )

        # Stdout logging still occurred
        assert len(capture_logs.records) == 1
        assert "subscription.created" in capture_logs.records[0].message

        # Database persistence was triggered
        mock_create_audit_log.assert_called_once()
        call_kwargs = mock_create_audit_log.call_args[1]
        assert call_kwargs["db"] == mock_db
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["action"] == "subscription.created"
        assert call_kwargs["resource_type"] == "subscription"
        assert call_kwargs["resource_id"] == str(subscription_id)
        assert call_kwargs["metadata"]["plan_name"] == "Pro"
