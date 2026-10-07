"""
Audit logging service for payment and subscription operations.

This module provides comprehensive audit logging with structured JSON format
for all payment, subscription, and administrative operations. It ensures
complete audit trails for compliance and debugging purposes, with dual emission:
writing structured JSON logs and persisting records into the PostgreSQL
audit_logs table when a database session is provided.

Usage:
    from src.services.audit_logger import audit_logger

    await audit_logger.log_subscription_created(
        user_id=user.id,
        subscription_id=subscription.id,
        plan_id=plan.id,
        plan_name=plan.name,
        billing_period="monthly",
        db=db,
    )
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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
    SUBSCRIPTION_RENEWED = "subscription.renewed"

    # Payment events
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_RECOVERED = "payment.recovered"
    PAYMENT_REFUNDED = "payment.refunded"

    # Refund lifecycle events
    REFUND_REQUESTED = "refund.requested"
    REFUND_APPROVED = "refund.approved"
    REFUND_REJECTED = "refund.rejected"
    REFUND_PROCESSED = "refund.processed"
    REFUND_FAILED = "refund.failed"
    REFUND_CANCELLED = "refund.cancelled"

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
    ADMIN_CREDITS_ADJUSTED = "admin.credits_adjusted"

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

    Provides structured logging with consistent format across all operations,
    and persists entries into the PostgreSQL audit_logs database table when
    a database session is supplied.
    """

    def __init__(self):
        """Initialize audit logger."""
        self.logger = logging.getLogger("audit")
        # Ensure audit logger is at INFO level
        if self.logger.level == logging.NOTSET:
            self.logger.setLevel(logging.INFO)

    async def _log_event(
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
        status: str = "success",
        error_message: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Any]:
        """
        Log an audit event with structured data and optional DB persistence.

        Args:
            event_type: Type of event (from AuditEventType enum)
            user_id: ID of user affected by the action
            admin_id: ID of admin performing the action (if applicable)
            resource_type: Type of resource (subscription, payment, license, refund, etc.)
            resource_id: ID of the resource
            changes: Dictionary of changes (before/after values)
            metadata: Additional contextual information
            ip_address: IP address of the actor
            user_agent: User agent of the actor
            status: Status of the action (success, failed, partial)
            error_message: Error message if failed
            db: Optional async database session for persistence to audit_logs
        """
        audit_data = {
            "event_type": event_type.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": str(user_id) if user_id else None,
            "admin_id": str(admin_id) if admin_id else None,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "changes": changes or {},
            "metadata": metadata or {},
            "ip_address": ip_address,
            "user_agent": user_agent,
            "status": status,
        }
        if error_message:
            audit_data["error_message"] = error_message

        # Remove None values to reduce log size
        audit_data = {k: v for k, v in audit_data.items() if v is not None}

        # Serialise the structured payload into the message itself for stdout/log files
        try:
            payload = json.dumps(audit_data, default=str, separators=(",", ":"))
        except (TypeError, ValueError):
            payload = str(audit_data)

        self.logger.info(
            f"AUDIT {event_type.value} {payload}",
            extra={"audit": audit_data},
        )

        # Persist to database if session is provided
        if db is not None:
            try:
                from src.utils.audit_helper import create_audit_log

                old_vals = None
                new_vals = None
                if changes:
                    if "plan" in changes or "billing_period" in changes:
                        old_vals = {
                            k: v.get("from")
                            for k, v in changes.items()
                            if isinstance(v, dict) and "from" in v
                        }
                        new_vals = {
                            k: v.get("to")
                            for k, v in changes.items()
                            if isinstance(v, dict) and "to" in v
                        }
                    else:
                        old_vals = changes.get("old_values") or changes
                        new_vals = changes.get("new_values")

                # Record customer user_id so user self-service can see their activity logs
                log_user_id = user_id or admin_id

                meta_copy = {**(metadata or {})}
                if admin_id and user_id and admin_id != user_id:
                    meta_copy["admin_id"] = str(admin_id)

                return await create_audit_log(
                    db=db,
                    user_id=log_user_id,
                    action=event_type.value,
                    resource_type=resource_type or "system",
                    resource_id=str(resource_id) if resource_id else "",
                    old_values=old_vals,
                    new_values=new_vals,
                    metadata=meta_copy,
                    status=status,
                    error_message=error_message,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            except Exception as e:
                logger.error(f"Failed to persist audit log for {event_type.value}: {e}")
                return None

        return None

    # Subscription audit methods

    async def log_subscription_created(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_id: Optional[UUID] = None,
        plan_name: Optional[str] = None,
        billing_period: Optional[str] = None,
        is_trial: bool = False,
        amount: Optional[int] = None,
        lemonsqueezy_subscription_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log subscription creation."""
        event_metadata: Dict[str, Any] = {
            "is_trial": is_trial,
            "amount": amount,
            "lemonsqueezy_subscription_id": lemonsqueezy_subscription_id,
            **(metadata or {}),
        }
        if plan_id is not None:
            event_metadata["plan_id"] = str(plan_id)
        if plan_name is not None:
            event_metadata["plan_name"] = plan_name
        if billing_period is not None:
            event_metadata["billing_period"] = billing_period

        await self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_CREATED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata=event_metadata,
            db=db,
        )

    async def log_subscription_updated(
        self,
        user_id: UUID,
        subscription_id: UUID,
        changes: Dict[str, Any],
        admin_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log subscription update with before/after values."""
        await self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_UPDATED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="subscription",
            resource_id=subscription_id,
            changes=changes,
            metadata=metadata,
            db=db,
        )

    async def log_subscription_cancelled(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_name: str,
        reason: Optional[str] = None,
        cancelled_by_admin: bool = False,
        admin_id: Optional[UUID] = None,
        cancel_immediately: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log subscription cancellation."""
        await self._log_event(
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
            },
            db=db,
        )

    async def log_subscription_upgraded(
        self,
        user_id: UUID,
        subscription_id: UUID,
        old_plan_name: str,
        new_plan_name: str,
        old_billing_period: str,
        new_billing_period: str,
        proration_amount: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log subscription upgrade."""
        await self._log_event(
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
            },
            db=db,
        )

    async def log_subscription_downgraded(
        self,
        user_id: UUID,
        subscription_id: UUID,
        old_plan_name: str,
        new_plan_name: str,
        old_billing_period: str,
        new_billing_period: str,
        effective_date: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log subscription downgrade."""
        await self._log_event(
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
            },
            db=db,
        )

    async def log_subscription_resumed(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log subscription resumption."""
        await self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_RESUMED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_name": plan_name,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_subscription_expired(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log subscription expiration."""
        await self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_EXPIRED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_name": plan_name,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_subscription_paused(
        self,
        user_id: UUID,
        subscription_id: UUID,
        resumes_at: Optional[datetime] = None,
        plan_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        resumes_str = (
            resumes_at.isoformat()
            if hasattr(resumes_at, "isoformat")
            else (str(resumes_at) if resumes_at else None)
        )
        await self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_PAUSED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_name": plan_name,
                "resumes_at": resumes_str,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_subscription_renewed(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_name: Optional[str] = None,
        amount: Optional[int] = None,
        currency: str = "USD",
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log subscription renewal."""
        await self._log_event(
            event_type=AuditEventType.SUBSCRIPTION_RENEWED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_name": plan_name,
                "amount": amount,
                "currency": currency,
                **(metadata or {}),
            },
            db=db,
        )

    # Payment audit methods

    async def log_payment_succeeded(
        self,
        user_id: UUID,
        subscription_id: UUID,
        amount: int,
        currency: str = "USD",
        lemonsqueezy_payment_id: Optional[str] = None,
        card_brand: Optional[str] = None,
        card_last_four: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log successful payment."""
        await self._log_event(
            event_type=AuditEventType.PAYMENT_SUCCEEDED,
            user_id=user_id,
            resource_type="payment",
            resource_id=subscription_id,
            metadata={
                "subscription_id": str(subscription_id),
                "amount": amount,
                "currency": currency,
                "lemonsqueezy_payment_id": lemonsqueezy_payment_id,
                "card_brand": card_brand,
                "card_last_four": card_last_four,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_payment_failed(
        self,
        user_id: UUID,
        subscription_id: UUID,
        amount: int,
        failure_reason: Optional[str] = None,
        lemonsqueezy_payment_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log failed payment."""
        await self._log_event(
            event_type=AuditEventType.PAYMENT_FAILED,
            user_id=user_id,
            resource_type="payment",
            resource_id=subscription_id,
            metadata={
                "subscription_id": str(subscription_id),
                "amount": amount,
                "failure_reason": failure_reason,
                "lemonsqueezy_payment_id": lemonsqueezy_payment_id,
                **(metadata or {}),
            },
            status="failed",
            error_message=failure_reason,
            db=db,
        )

    async def log_payment_recovered(
        self,
        user_id: UUID,
        subscription_id: UUID,
        amount: Optional[int] = None,
        currency: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log recovered subscription payment."""
        event_metadata: Dict[str, Any] = {
            "subscription_id": str(subscription_id),
            **(metadata or {}),
        }
        if amount is not None:
            event_metadata["amount"] = amount
        if currency is not None:
            event_metadata["currency"] = currency

        await self._log_event(
            event_type=AuditEventType.PAYMENT_RECOVERED,
            user_id=user_id,
            resource_type="payment",
            resource_id=subscription_id,
            metadata=event_metadata,
            db=db,
        )

    async def log_payment_refunded(
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
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log payment refund."""
        await self._log_event(
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
            },
            db=db,
        )

    # Refund lifecycle methods

    async def log_refund_requested(
        self,
        user_id: UUID,
        refund_request_id: UUID,
        order_id: str,
        amount: int,
        currency: str = "USD",
        reason: Optional[str] = None,
        requested_by_admin: bool = False,
        admin_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log refund request creation."""
        await self._log_event(
            event_type=AuditEventType.REFUND_REQUESTED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="refund",
            resource_id=refund_request_id,
            metadata={
                "refund_request_id": str(refund_request_id),
                "order_id": order_id,
                "amount": amount,
                "currency": currency,
                "reason": reason,
                "requested_by_admin": requested_by_admin,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_refund_approved(
        self,
        admin_id: UUID,
        user_id: UUID,
        refund_request_id: UUID,
        order_id: str,
        amount: int,
        currency: str = "USD",
        admin_note: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log refund request approval."""
        await self._log_event(
            event_type=AuditEventType.REFUND_APPROVED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="refund",
            resource_id=refund_request_id,
            metadata={
                "refund_request_id": str(refund_request_id),
                "order_id": order_id,
                "amount": amount,
                "currency": currency,
                "admin_note": admin_note,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_refund_rejected(
        self,
        admin_id: UUID,
        user_id: UUID,
        refund_request_id: UUID,
        order_id: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log refund request rejection."""
        await self._log_event(
            event_type=AuditEventType.REFUND_REJECTED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="refund",
            resource_id=refund_request_id,
            metadata={
                "refund_request_id": str(refund_request_id),
                "order_id": order_id,
                "reason": reason,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_refund_cancelled(
        self,
        admin_id: UUID,
        user_id: UUID,
        refund_request_id: UUID,
        order_id: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log refund request unapproved/cancelled."""
        await self._log_event(
            event_type=AuditEventType.REFUND_CANCELLED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="refund",
            resource_id=refund_request_id,
            metadata={
                "refund_request_id": str(refund_request_id),
                "order_id": order_id,
                "reason": reason,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_refund_processed(
        self,
        user_id: UUID,
        refund_id: UUID,
        amount: int,
        currency: str = "USD",
        order_id: Optional[str] = None,
        admin_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log refund processed."""
        await self._log_event(
            event_type=AuditEventType.REFUND_PROCESSED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="refund",
            resource_id=refund_id,
            metadata={
                "refund_id": str(refund_id),
                "order_id": order_id,
                "amount": amount,
                "currency": currency,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_refund_failed(
        self,
        user_id: UUID,
        refund_id: UUID,
        amount: int,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log failed refund attempt."""
        await self._log_event(
            event_type=AuditEventType.REFUND_FAILED,
            user_id=user_id,
            resource_type="refund",
            resource_id=refund_id,
            metadata={
                "amount": amount,
                "reason": reason,
                **(metadata or {}),
            },
            status="failed",
            error_message=reason,
            db=db,
        )

    # Checkout audit methods

    async def log_checkout_created(
        self,
        user_id: UUID,
        plan_id: UUID,
        plan_name: str,
        billing_period: str,
        checkout_url: str,
        discount_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log checkout session creation."""
        await self._log_event(
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
            },
            db=db,
        )

    # Webhook audit methods

    async def log_webhook_received(
        self,
        event_id: str,
        event_name: str,
        signature_valid: bool,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log webhook event receipt."""
        await self._log_event(
            event_type=AuditEventType.WEBHOOK_RECEIVED,
            resource_type="webhook",
            metadata={
                "event_id": event_id,
                "event_name": event_name,
                "signature_valid": signature_valid,
                **(metadata or {}),
            },
            ip_address=ip_address,
            db=db,
        )

    async def log_webhook_processed(
        self,
        event_id: str,
        event_name: str,
        processing_time_ms: float,
        user_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log successful webhook processing."""
        await self._log_event(
            event_type=AuditEventType.WEBHOOK_PROCESSED,
            user_id=user_id,
            resource_type="webhook",
            metadata={
                "event_id": event_id,
                "event_name": event_name,
                "processing_time_ms": processing_time_ms,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_webhook_failed(
        self,
        event_id: str,
        event_name: str,
        error: str,
        retry_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log webhook processing failure."""
        await self._log_event(
            event_type=AuditEventType.WEBHOOK_FAILED,
            resource_type="webhook",
            metadata={
                "event_id": event_id,
                "event_name": event_name,
                "error": error,
                "retry_count": retry_count,
                **(metadata or {}),
            },
            status="failed",
            error_message=error,
            db=db,
        )

    # Admin action audit methods

    async def log_admin_refund_created(
        self,
        admin_id: UUID,
        user_id: UUID,
        refund_id: UUID,
        subscription_id: Optional[UUID],
        amount: int,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log admin-initiated refund."""
        await self._log_event(
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
            db=db,
        )

    async def log_admin_subscription_extended(
        self,
        admin_id: UUID,
        user_id: UUID,
        subscription_id: UUID,
        extend_days: int,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log admin-initiated subscription extension."""
        await self._log_event(
            event_type=AuditEventType.ADMIN_SUBSCRIPTION_EXTENDED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "extend_days": extend_days,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_admin_subscription_cancelled(
        self,
        admin_id: UUID,
        user_id: UUID,
        subscription_id: UUID,
        reason: str,
        cancel_immediately: bool = False,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log admin-initiated subscription cancellation."""
        await self._log_event(
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
            db=db,
        )

    async def log_admin_credits_adjusted(
        self,
        admin_id: UUID,
        user_id: UUID,
        subscription_id: UUID,
        action: str,
        amount: int,
        balance_before: int,
        balance_after: int,
        reason: str,
        grant_id: Optional[UUID] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Any]:
        """Log a super admin adding, deducting or resetting a user's credits.

        Recorded against the affected user, the admin in the metadata. Returns the
        audit row when it was written to ``db``.
        """
        return await self._log_event(
            event_type=AuditEventType.ADMIN_CREDITS_ADJUSTED,
            user_id=user_id,
            admin_id=admin_id,
            resource_type="subscription",
            resource_id=subscription_id,
            changes={
                "old_values": {"balance": balance_before},
                "new_values": {"balance": balance_after},
            },
            metadata={
                "admin_id": str(admin_id),
                "action": action,
                "amount": amount,
                "balance_before": balance_before,
                "balance_after": balance_after,
                "reason": reason,
                "grant_id": str(grant_id) if grant_id else None,
                "expires_at": expires_at.isoformat() if expires_at else None,
                **(metadata or {}),
            },
            db=db,
        )

    # License audit methods

    async def log_license_activated(
        self,
        user_id: UUID,
        license_id: UUID,
        instance_id: str,
        instance_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log license activation."""
        await self._log_event(
            event_type=AuditEventType.LICENSE_ACTIVATED,
            user_id=user_id,
            resource_type="license",
            resource_id=license_id,
            metadata={
                "instance_id": instance_id,
                "instance_name": instance_name,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_license_deactivated(
        self,
        user_id: UUID,
        license_id: UUID,
        instance_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log license deactivation."""
        await self._log_event(
            event_type=AuditEventType.LICENSE_DEACTIVATED,
            user_id=user_id,
            resource_type="license",
            resource_id=license_id,
            metadata={
                "instance_id": instance_id,
                **(metadata or {}),
            },
            db=db,
        )

    # Trial audit methods

    async def log_trial_started(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_name: str,
        trial_days: int,
        trial_end_date: datetime,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log trial start."""
        await self._log_event(
            event_type=AuditEventType.TRIAL_STARTED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_name": plan_name,
                "trial_days": trial_days,
                "trial_end_date": trial_end_date.isoformat() if trial_end_date else None,
                **(metadata or {}),
            },
            db=db,
        )

    async def log_trial_converted(
        self,
        user_id: UUID,
        subscription_id: UUID,
        plan_name: str,
        metadata: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Log trial conversion to paid."""
        await self._log_event(
            event_type=AuditEventType.TRIAL_CONVERTED,
            user_id=user_id,
            resource_type="subscription",
            resource_id=subscription_id,
            metadata={
                "plan_name": plan_name,
                **(metadata or {}),
            },
            db=db,
        )


# Singleton instance for easy import
audit_logger = AuditLogger()
