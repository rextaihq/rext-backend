"""
Tests for audit logging service.

Tests comprehensive audit logging for all payment, subscription, webhook,
and administrative operations.
"""

import logging
from datetime import datetime
from uuid import uuid4
import pytest

from src.services.audit_logger import AuditLogger, AuditEventType


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

    def test_log_subscription_created(self, audit_logger, capture_logs):
        """Test subscription creation audit log."""
        user_id = uuid4()
        subscription_id = uuid4()
        plan_id = uuid4()

        audit_logger.log_subscription_created(
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

    def test_log_subscription_cancelled(self, audit_logger, capture_logs):
        """Test subscription cancellation audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        audit_logger.log_subscription_cancelled(
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

    def test_log_subscription_upgraded(self, audit_logger, capture_logs):
        """Test subscription upgrade audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        audit_logger.log_subscription_upgraded(
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

    def test_log_payment_succeeded(self, audit_logger, capture_logs):
        """Test successful payment audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        audit_logger.log_payment_succeeded(
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

    def test_log_payment_failed(self, audit_logger, capture_logs):
        """Test failed payment audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        audit_logger.log_payment_failed(
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

    def test_log_payment_refunded(self, audit_logger, capture_logs):
        """Test payment refund audit log."""
        user_id = uuid4()
        refund_id = uuid4()
        subscription_id = uuid4()
        admin_id = uuid4()

        audit_logger.log_payment_refunded(
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

    def test_log_checkout_created(self, audit_logger, capture_logs):
        """Test checkout creation audit log."""
        user_id = uuid4()
        plan_id = uuid4()

        audit_logger.log_checkout_created(
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

    def test_log_webhook_received(self, audit_logger, capture_logs):
        """Test webhook received audit log."""
        audit_logger.log_webhook_received(
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

    def test_log_webhook_processed(self, audit_logger, capture_logs):
        """Test webhook processed audit log."""
        user_id = uuid4()

        audit_logger.log_webhook_processed(
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

    def test_log_webhook_failed(self, audit_logger, capture_logs):
        """Test webhook failed audit log."""
        audit_logger.log_webhook_failed(
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

    def test_log_admin_refund_created(self, audit_logger, capture_logs):
        """Test admin refund creation audit log."""
        admin_id = uuid4()
        user_id = uuid4()
        refund_id = uuid4()
        subscription_id = uuid4()

        audit_logger.log_admin_refund_created(
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

    def test_log_admin_subscription_cancelled(self, audit_logger, capture_logs):
        """Test admin subscription cancellation audit log."""
        admin_id = uuid4()
        user_id = uuid4()
        subscription_id = uuid4()

        audit_logger.log_admin_subscription_cancelled(
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

    def test_log_license_activated(self, audit_logger, capture_logs):
        """Test license activation audit log."""
        user_id = uuid4()
        license_id = uuid4()

        audit_logger.log_license_activated(
            user_id=user_id,
            license_id=license_id,
            instance_id="device-001",
            instance_name="MacBook Pro",
        )

        assert len(capture_logs.records) == 1
        log_record = capture_logs.records[0]
        assert "license.activated" in log_record.message

        audit_data = log_record.__dict__["audit"]
        assert audit_data["event_type"] == "license.activated"
        assert audit_data["metadata"]["instance_id"] == "device-001"
        assert audit_data["metadata"]["instance_name"] == "MacBook Pro"

    def test_log_trial_started(self, audit_logger, capture_logs):
        """Test trial start audit log."""
        user_id = uuid4()
        subscription_id = uuid4()
        trial_end_date = datetime(2025, 11, 1)

        audit_logger.log_trial_started(
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

    def test_log_trial_converted(self, audit_logger, capture_logs):
        """Test trial conversion audit log."""
        user_id = uuid4()
        subscription_id = uuid4()

        audit_logger.log_trial_converted(
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

    def test_structured_logging_format(self, audit_logger, capture_logs):
        """Test that audit logs use structured JSON format."""
        user_id = uuid4()
        subscription_id = uuid4()

        audit_logger.log_subscription_created(
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

    def test_none_values_excluded(self, audit_logger, capture_logs):
        """Test that None values are excluded from audit logs."""
        user_id = uuid4()
        subscription_id = uuid4()

        # Log with minimal parameters (no admin_id, no ip_address)
        audit_logger.log_subscription_cancelled(
            user_id=user_id,
            subscription_id=subscription_id,
            plan_name="Pro",
        )

        log_record = capture_logs.records[0]
        audit_data = log_record.__dict__["audit"]

        # Verify None values are not present
        assert "admin_id" not in audit_data
        assert "ip_address" not in audit_data
        # But required fields should be present
        assert "user_id" in audit_data
        assert "event_type" in audit_data
