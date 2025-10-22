"""
Audit logging service for payment and subscription operations.

This module provides comprehensive audit logging with structured JSON format
for all payment, subscription, and administrative operations. It ensures
complete audit trails for compliance and debugging purposes.

Usage:
    from src.services.audit_logger import AuditLogger

    audit = AuditLogger()
    await audit.log_subscription_created(
        user_id=user.id,
        subscription_id=subscription.id,
        plan_id=plan.id,
        billing_period="monthly"
    )
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Audit event types for categorization and filtering."""

    # Subscription events
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_UPDATED = "subscription.updated"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    SUBSCRIPTION_RESUMED = "subscription.resumed"
    SUBSCRIPTION_EXPIRED = "subscription.expired"
    SUBSCRIPTION_PAUSED = "subscription.paused"
    SUBSCRIPTION_UPGRADED = "subscription.upgraded"
    SUBSCRIPTION_DOWNGRADED = "subscription.downgraded"

    # Payment events
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_RECOVERED = "payment.recovered"
    PAYMENT_REFUNDED = "payment.refunded"

    # Checkout events
    CHECKOUT_CREATED = "checkout.created"
    CHECKOUT_COMPLETED = "checkout.completed"
    CHECKOUT_ABANDONED = "checkout.abandoned"

    # Webhook events
    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_PROCESSED = "webhook.processed"
    WEBHOOK_FAILED = "webhook.failed"
    WEBHOOK_SIGNATURE_INVALID = "webhook.signature_invalid"

    # Admin actions
    ADMIN_REFUND_CREATED = "admin.refund_created"
    ADMIN_SUBSCRIPTION_EXTENDED = "admin.subscription_extended"
    ADMIN_SUBSCRIPTION_CANCELLED = "admin.subscription_cancelled"
    ADMIN_USER_MIGRATED = "admin.user_migrated"
    ADMIN_PLAN_CHANGED = "admin.plan_changed"

    # License events
    LICENSE_CREATED = "license.created"
    LICENSE_ACTIVATED = "license.activated"
    LICENSE_DEACTIVATED = "license.deactivated"
    LICENSE_REVOKED = "license.revoked"

    # Trial events
    TRIAL_STARTED = "trial.started"
    TRIAL_CONVERTED = "trial.converted"
    TRIAL_EXPIRED = "trial.expired"

    # User actions
    USER_PORTAL_ACCESSED = "user.portal_accessed"
    USER_INVOICE_DOWNLOADED = "user.invoice_downloaded"
    USER_PLAN_VIEWED = "user.plan_viewed"


class AuditLogger:
    """
    Comprehensive audit logger for payment and subscription operations.

    Provides structured logging with consistent format across all operations.
    All logs include:
    - Timestamp
    - Event type
    - User ID (if applicable)
    - Resource IDs (subscription_id, plan_id, etc.)
    - Changes (before/after states)
    - Actor (user or admin)
    - Additional metadata
    """

    def __init__(self):
        """Initialize audit logger."""
        self.logger = logging.getLogger("audit")
        # Ensure audit logger is at INFO level
        if self.logger.level == logging.NOTSET:
            self.logger.setLevel(logging.INFO)

    def _log_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[UUID] = None,
        admin_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        changes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Log an audit event with structured data.

        Args:
            event_type: Type of event (from AuditEventType enum)
            user_id: ID of user affected by the action
            admin_id: ID of admin performing the action (if applicable)
            resource_type: Type of resource (subscription, payment, license, etc.)
            resource_id: ID of the resource
            changes: Dictionary of changes (before/after values)
            metadata: Additional contextual information
            ip_address: IP address of the actor
            user_agent: User agent of the actor
        """
        audit_data = {
            "event_type": event_type.value,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": str(user_id) if user_id else None,
            "admin_id": str(admin_id) if admin_id else None,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "changes": changes or {},
            "metadata": metadata or {},
            "ip_address": ip_address,
            "user_agent": user_agent,
        }

        # Remove None values to reduce log size
        audit_data = {k: v for k, v in audit_data.items() if v is not None}

        # Log with structured extra data
        self.logger.info(
            f"AUDIT: {event_type.value}",
            extra={"audit": audit_data}
        )

    # Subscription audit methods

    def log_subscription_created(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_id: UUID,
        plan_name: str,
        billing_period: str,
        is_trial: bool = False,
        amount: Optional[int] = None,
        lemonsqueezy_subscription_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log subscription creation."""
        self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_CREATED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_id": str(plan_id),
                "plan_name": plan_name,
                "billing_period": billing_period,
                "is_trial": is_trial,
                "amount": amount,
                "lemonsqueezy_subscription_id": lemonsqueezy_subscription_id,
                **(metadata or {}),
            }
        )

    def log_subscription_updated(
        self,
        user_id: UUID,
        subscription_id: UUID,
        changes: Dict[str, Any],
        admin_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log subscription update with before/after values."""
        self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_UPDATED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="subscription",
            resource_id=subscription_id,
            changes=changes,
            metadata=metadata,
        )

    def log_subscription_cancelled(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_name: str,
        reason: Optional[str] = None,
        cancelled_by_admin: bool = False,
        admin_id: Optional[UUID] = None,
        cancel_immediately: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log subscription cancellation."""
        self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_CANCELLED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_name": plan_name,
                "reason": reason,
                "cancelled_by_admin": cancelled_by_admin,
                "cancel_immediately": cancel_immediately,
                **(metadata or {}),
            }
        )

    def log_subscription_upgraded(
        self,
        user_id: UUID,
        subscription_id: UUID,
        old_plan_name: str,
        new_plan_name: str,
        old_billing_period: str,
        new_billing_period: str,
        proration_amount: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log subscription upgrade."""
        self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_UPGRADED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            changes={
                "plan": {"from": old_plan_name, "to": new_plan_name},
                "billing_period": {"from": old_billing_period, "to": new_billing_period},
            },
            metadata={
                "proration_amount": proration_amount,
                **(metadata or {}),
            }
        )

    def log_subscription_downgraded(
        self,
        user_id: UUID,
        subscription_id: UUID,
        old_plan_name: str,
        new_plan_name: str,
        old_billing_period: str,
        new_billing_period: str,
        effective_date: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log subscription downgrade."""
        self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_DOWNGRADED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            changes={
                "plan": {"from": old_plan_name, "to": new_plan_name},
                "billing_period": {"from": old_billing_period, "to": new_billing_period},
            },
            metadata={
                "effective_date": effective_date.isoformat() if effective_date else None,
                **(metadata or {}),
            }
        )

    # Payment audit methods

    def log_payment_succeeded(
        self,
        user_id: UUID,
        subscription_id: UUID,
        amount: int,
        currency: str = "USD",
        lemonsqueezy_payment_id: Optional[str] = None,
        card_brand: Optional[str] = None,
        card_last_four: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log successful payment."""
        self._log_event(
            event_type=AuditEventType.PAYMENT_SUCCEEDED,
            user_id=user_id,
            resource_type="payment",
            metadata={
                "subscription_id": str(subscription_id),
                "amount": amount,
                "currency": currency,
                "lemonsqueezy_payment_id": lemonsqueezy_payment_id,
                "card_brand": card_brand,
                "card_last_four": card_last_four,
                **(metadata or {}),
            }
        )

    def log_payment_failed(
        self,
        user_id: UUID,
        subscription_id: UUID,
        amount: int,
        failure_reason: Optional[str] = None,
        lemonsqueezy_payment_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log failed payment."""
        self._log_event(
            event_type=AuditEventType.PAYMENT_FAILED,
            user_id=user_id,
            resource_type="payment",
            metadata={
                "subscription_id": str(subscription_id),
                "amount": amount,
                "failure_reason": failure_reason,
                "lemonsqueezy_payment_id": lemonsqueezy_payment_id,
                **(metadata or {}),
            }
        )

    def log_payment_refunded(
        self,
        user_id: UUID,
        refund_id: UUID,
        subscription_id: Optional[UUID],
        amount: int,
        reason: Optional[str] = None,
        is_partial: bool = False,
        admin_id: Optional[UUID] = None,
        lemonsqueezy_refund_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log payment refund."""
        self._log_event(
            event_type=AuditEventType.PAYMENT_REFUNDED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="refund",
            resource_id=refund_id,
            metadata={
                "subscription_id": str(subscription_id) if subscription_id else None,
                "amount": amount,
                "reason": reason,
                "is_partial": is_partial,
                "lemonsqueezy_refund_id": lemonsqueezy_refund_id,
                **(metadata or {}),
            }
        )

    # Checkout audit methods

    def log_checkout_created(
        self,
        user_id: UUID,
        plan_id: UUID,
        plan_name: str,
        billing_period: str,
        checkout_url: str,
        discount_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log checkout session creation."""
        self._log_event(
            event_type=AuditEventType.CHECKOUT_CREATED,
            user_id=user_id,
            resource_type="checkout",
            metadata={
                "plan_id": str(plan_id),
                "plan_name": plan_name,
                "billing_period": billing_period,
                "checkout_url": checkout_url,
                "discount_code": discount_code,
                **(metadata or {}),
            }
        )

    # Webhook audit methods

    def log_webhook_received(
        self,
        event_id: str,
        event_name: str,
        signature_valid: bool,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log webhook event receipt."""
        self._log_event(
            event_type=AuditEventType.WEBHOOK_RECEIVED,
            resource_type="webhook",
            metadata={
                "event_id": event_id,
                "event_name": event_name,
                "signature_valid": signature_valid,
                **(metadata or {}),
            },
            ip_address=ip_address,
        )

    def log_webhook_processed(
        self,
        event_id: str,
        event_name: str,
        processing_time_ms: float,
        user_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log successful webhook processing."""
        self._log_event(
            event_type=AuditEventType.WEBHOOK_PROCESSED,
            user_id=user_id,
            resource_type="webhook",
            metadata={
                "event_id": event_id,
                "event_name": event_name,
                "processing_time_ms": processing_time_ms,
                **(metadata or {}),
            }
        )

    def log_webhook_failed(
        self,
        event_id: str,
        event_name: str,
        error: str,
        retry_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log webhook processing failure."""
        self._log_event(
            event_type=AuditEventType.WEBHOOK_FAILED,
            resource_type="webhook",
            metadata={
                "event_id": event_id,
                "event_name": event_name,
                "error": error,
                "retry_count": retry_count,
                **(metadata or {}),
            }
        )

    # Admin action audit methods

    def log_admin_refund_created(
        self,
        admin_id: UUID,
        user_id: UUID,
        refund_id: UUID,
        subscription_id: Optional[UUID],
        amount: int,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log admin-initiated refund."""
        self._log_event(
            event_type=AuditEventType.ADMIN_REFUND_CREATED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="refund",
            resource_id=refund_id,
            metadata={
                "subscription_id": str(subscription_id) if subscription_id else None,
                "amount": amount,
                "reason": reason,
                **(metadata or {}),
            },
            ip_address=ip_address,
        )

    def log_admin_subscription_cancelled(
        self,
        admin_id: UUID,
        user_id: UUID,
        subscription_id: UUID,
        reason: str,
        cancel_immediately: bool = False,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log admin-initiated subscription cancellation."""
        self._log_event(
            event_type=AuditEventType.ADMIN_SUBSCRIPTION_CANCELLED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "reason": reason,
                "cancel_immediately": cancel_immediately,
                **(metadata or {}),
            },
            ip_address=ip_address,
        )

    # License audit methods

    def log_license_activated(
        self,
        user_id: UUID,
        license_id: UUID,
        instance_id: str,
        instance_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log license activation."""
        self._log_event(
            event_type=AuditEventType.LICENSE_ACTIVATED,
            user_id=user_id,
            resource_type="license",
            resource_id=license_id,
            metadata={
                "instance_id": instance_id,
                "instance_name": instance_name,
                **(metadata or {}),
            }
        )

    def log_license_deactivated(
        self,
        user_id: UUID,
        license_id: UUID,
        instance_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log license deactivation."""
        self._log_event(
            event_type=AuditEventType.LICENSE_DEACTIVATED,
            user_id=user_id,
            resource_type="license",
            resource_id=license_id,
            metadata={
                "instance_id": instance_id,
                **(metadata or {}),
            }
        )

    # Trial audit methods

    def log_trial_started(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_name: str,
        trial_days: int,
        trial_end_date: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log trial start."""
        self._log_event(
            event_type=AuditEventType.TRIAL_STARTED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_name": plan_name,
                "trial_days": trial_days,
                "trial_end_date": trial_end_date.isoformat(),
                **(metadata or {}),
            }
        )

    def log_trial_converted(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log trial conversion to paid."""
        self._log_event(
            event_type=AuditEventType.TRIAL_CONVERTED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_name": plan_name,
                **(metadata or {}),
            }
        )


# Singleton instance for easy import
audit_logger = AuditLogger()
