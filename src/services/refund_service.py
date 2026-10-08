"""
Refund Service

Handles refund operations including:
- Recording refunds against LemonSqueezy's own cumulative totals
- Reporting how much of an order has been refunded and how much remains
- Listing refund history for the admin views
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence
from uuid import UUID

from sqlalchemy import Integer, and_, cast, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.api.models.subscription_models.refunds import Refund, RefundStatus
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.services.webhook_monitoring_service import _mask_email
from src.utils.logger import logger


class RefundService:
    """Service for managing refunds."""

    def __init__(self, db: AsyncSession):
        """
        Initialize refund service.

        Args:
            db: Database session
        """
        self.db = db

    async def mark_refund_completed(
        self, refund_id: UUID, lemonsqueezy_refund_id: Optional[str] = None
    ) -> Refund:
        """
        Mark a refund as completed.

        Args:
            refund_id: Refund ID
            lemonsqueezy_refund_id: LemonSqueezy refund ID (optional)

        Returns:
            Refund: Updated refund record
        """
        stmt = select(Refund).where(Refund.id == refund_id)
        result = await self.db.execute(stmt)
        refund = result.scalar_one_or_none()

        if not refund:
            raise ValueError(f"Refund {refund_id} not found")

        refund.status = RefundStatus.COMPLETED
        refund.processed_at = datetime.now(timezone.utc)
        if lemonsqueezy_refund_id:
            refund.lemonsqueezy_refund_id = lemonsqueezy_refund_id
        refund.updated_at = datetime.now(timezone.utc)

        await self.db.flush()

        logger.info(f"Marked refund {refund_id} as completed", extra={"refund_id": str(refund_id)})

        return refund

    async def mark_refund_failed(self, refund_id: UUID, reason: Optional[str] = None) -> Refund:
        """
        Mark a refund as failed.

        Args:
            refund_id: Refund ID
            reason: Failure reason

        Returns:
            Refund: Updated refund record
        """
        stmt = select(Refund).where(Refund.id == refund_id)
        result = await self.db.execute(stmt)
        refund = result.scalar_one_or_none()

        if not refund:
            raise ValueError(f"Refund {refund_id} not found")

        refund.status = RefundStatus.FAILED
        if reason:
            refund.reason = f"{refund.reason or ''}\nFailure: {reason}".strip()
        refund.updated_at = datetime.now(timezone.utc)

        await self.db.flush()

        logger.warning(
            f"Marked refund {refund_id} as failed: {reason}",
            extra={"refund_id": str(refund_id), "reason": reason},
        )

        return refund

    async def get_refunded_total(self, lemonsqueezy_order_id: str) -> int:
        """Cents already refunded against one order.

        An order can have many refund rows once partials are in play, so this
        returns the sum rather than "the" refund. Failed attempts are excluded:
        no money moved, so they must not consume refundable balance.
        """
        totals = await self.get_refunded_totals([lemonsqueezy_order_id])
        return totals.get(str(lemonsqueezy_order_id), 0)

    async def get_refunded_totals(self, lemonsqueezy_order_ids: Sequence[str]) -> Dict[str, int]:
        """Cents refunded per order id, for a batch of orders.

        One query for a whole page of orders rather than one per row.
        """
        ids = [str(order_id) for order_id in lemonsqueezy_order_ids if order_id]
        if not ids:
            return {}

        result = await self.db.execute(
            select(
                Refund.lemonsqueezy_order_id,
                func.coalesce(func.sum(Refund.refund_amount), 0),
            )
            .where(
                Refund.lemonsqueezy_order_id.in_(ids),
                Refund.status != RefundStatus.FAILED,
            )
            .group_by(Refund.lemonsqueezy_order_id)
        )
        return {row[0]: int(row[1] or 0) for row in result.all()}

    async def lock_order(self, lemonsqueezy_order_id: str) -> None:
        """One recorder at a time per order, until this transaction ends.

        Recording reads the recorded total and then inserts, which is not atomic,
        and two events for one refund run in their own transactions (a first
        payment's order_refunded and subscription_payment_refunded, or the webhook
        racing the admin's refund that caused it). The second waits here, then
        reads what the first committed and records nothing.

        ``record_provider_refund`` takes it itself. A handler that also locks the
        subscription's row takes this first, as the recorders that write the
        subscription afterwards do: in the other order, two handlers of one refund
        would each hold what the other waits for.
        """
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"refund:{lemonsqueezy_order_id}"},
        )

    async def record_provider_refund(
        self,
        *,
        lemonsqueezy_order_id: str,
        user_id: UUID,
        provider_refunded_total: int,
        original_amount: int,
        subscription_id: Optional[UUID] = None,
        reason: Optional[str] = None,
        lemonsqueezy_refund_id: Optional[str] = None,
        currency: str = "USD",
        refunded_at: Optional[datetime] = None,
    ) -> Optional[Refund]:
        """Bring our refund rows in line with LemonSqueezy's own total.

        LemonSqueezy never reports an individual refund: both the refund API
        response and the `order_refunded` webhook carry the order's
        *cumulative* ``refunded_amount``. The difference against what we have
        already recorded is therefore exactly the new refund.

        That difference is also what makes this idempotent: a replayed webhook,
        or the webhook arriving after the API call that caused it, computes a
        delta of zero and writes nothing. Duplicate events can neither
        duplicate refunds nor inflate the refunded total.

        Args:
            lemonsqueezy_order_id: The order the refund is against.
            user_id: User being refunded.
            provider_refunded_total: Cumulative cents refunded, per LemonSqueezy.
            original_amount: The order total in cents.
            subscription_id: Local subscription, when the order came from one.
            reason: Refund reason, stored on the new row.
            lemonsqueezy_refund_id: Provider reference, when we have one.
            currency: ISO currency code.
            refunded_at: When the money moved, per LemonSqueezy.

        Returns:
            The refund row created for the new money, or None when this call
            carried nothing we had not already recorded.
        """
        await self.lock_order(lemonsqueezy_order_id)
        already_refunded = await self.get_refunded_total(lemonsqueezy_order_id)
        delta = int(provider_refunded_total or 0) - already_refunded

        if delta <= 0:
            logger.info(
                f"Refund for order {lemonsqueezy_order_id} already recorded "
                f"(provider total {provider_refunded_total}, ours {already_refunded})",
                extra={"order_id": lemonsqueezy_order_id},
            )
            return None

        refund = Refund(
            user_id=user_id,
            subscription_id=subscription_id,
            lemonsqueezy_order_id=str(lemonsqueezy_order_id),
            lemonsqueezy_refund_id=lemonsqueezy_refund_id,
            refund_amount=delta,
            original_amount=original_amount,
            currency=currency,
            reason=reason,
            # Partial while the order still has a refundable balance after this
            # refund, rather than by comparing one row against the order total.
            is_partial=int(provider_refunded_total or 0) < original_amount,
            status=RefundStatus.COMPLETED,
            processed_at=refunded_at or datetime.now(timezone.utc),
        )
        self.db.add(refund)
        await self.db.flush()

        logger.info(
            f"Recorded refund {refund.id} of {delta} cents for order {lemonsqueezy_order_id}",
            extra={
                "refund_id": str(refund.id),
                "order_id": lemonsqueezy_order_id,
                "amount": delta,
                "provider_total": provider_refunded_total,
            },
        )
        return refund

    async def list_refunds(
        self,
        user_id: Optional[UUID] = None,
        subscription_id: Optional[UUID] = None,
        status: Optional[str] = None,
        is_partial: Optional[bool] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """
        List refunds with filtering and pagination.

        Args:
            user_id: Filter by user ID
            subscription_id: Filter by subscription ID
            status: Filter by status
            is_partial: Filter by partial refund status
            start_date: Filter by start date
            end_date: Filter by end date
            page: Page number
            per_page: Items per page

        Returns:
            Dict with refunds, pagination, and summary
        """
        # Build filters
        filters = []
        if user_id:
            filters.append(Refund.user_id == user_id)
        if subscription_id:
            filters.append(Refund.subscription_id == subscription_id)
        if status:
            if isinstance(status, str):
                try:
                    status = RefundStatus(status)
                except ValueError:
                    pass  # Let it fail at query time if invalid
            filters.append(Refund.status == status)
        if is_partial is not None:
            filters.append(Refund.is_partial == is_partial)
        if start_date:
            filters.append(Refund.created_at >= start_date)
        if end_date:
            filters.append(Refund.created_at <= end_date)

        # Count total
        count_query = select(func.count(Refund.id))
        if filters:
            count_query = count_query.where(and_(*filters))
        total_result = await self.db.execute(count_query)
        total_refunds = total_result.scalar() or 0

        # Get paginated refunds with relationshipss
        offset = (page - 1) * per_page
        query = (
            select(Refund)
            .options(
                joinedload(Refund.user),
                joinedload(Refund.subscription).joinedload(UserSubscription.plan),
            )
            .order_by(desc(Refund.created_at))
            .offset(offset)
            .limit(per_page)
        )

        if filters:
            query = query.where(and_(*filters))

        result = await self.db.execute(query)
        refunds = result.scalars().unique().all()

        # Calculate summary statistics
        summary_query = select(
            func.count(Refund.id).label("total"),
            func.sum(Refund.refund_amount).label("total_amount"),
            func.sum(cast(Refund.is_partial, Integer)).label("partial_count"),
            func.sum(cast(Refund.status == RefundStatus.COMPLETED, Integer)).label(
                "completed_count"
            ),
            func.sum(cast(Refund.status == RefundStatus.PENDING, Integer)).label("pending_count"),
            func.sum(cast(Refund.status == RefundStatus.FAILED, Integer)).label("failed_count"),
        )

        if filters:
            summary_query = summary_query.where(and_(*filters))

        summary_result = await self.db.execute(summary_query)
        summary_row = summary_result.first()

        summary = {
            "total_refunds": summary_row.total or 0,
            "total_amount": summary_row.total_amount or 0,
            "partial_refunds": summary_row.partial_count or 0,
            "completed_refunds": summary_row.completed_count or 0,
            "pending_refunds": summary_row.pending_count or 0,
            "failed_refunds": summary_row.failed_count or 0,
        }

        # Build response
        refunds_data = []
        for refund in refunds:
            refund_dict = refund.to_dict()

            # Add user details
            if refund.user:
                refund_dict["user_email"] = refund.user.email
                refund_dict["user_email_masked"] = _mask_email(refund.user.email)
                refund_dict["user_name"] = (
                    refund.user.full_name or refund.user.display_name or "***"
                )

            # Add plan details
            if refund.subscription and refund.subscription.plan:
                refund_dict["plan_name"] = refund.subscription.plan.name

            refunds_data.append(refund_dict)

        return {
            "refunds": refunds_data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_refunds,
                "total_pages": (total_refunds + per_page - 1) // per_page,
            },
            "summary": summary,
        }

    async def get_refund(self, refund_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get a single refund by ID with full details.

        Args:
            refund_id: Refund ID

        Returns:
            Refund details or None
        """
        stmt = (
            select(Refund)
            .options(
                joinedload(Refund.user),
                joinedload(Refund.subscription).joinedload(UserSubscription.plan),
            )
            .where(Refund.id == refund_id)
        )

        result = await self.db.execute(stmt)
        refund = result.scalar_one_or_none()

        if not refund:
            return None

        refund_dict = refund.to_dict()

        # Add user details
        if refund.user:
            refund_dict["user_email"] = refund.user.email
            refund_dict["user_email_masked"] = _mask_email(refund.user.email)
            refund_dict["user_name"] = refund.user.full_name or refund.user.display_name or "***"

        # Add plan details
        if refund.subscription and refund.subscription.plan:
            refund_dict["plan_name"] = refund.subscription.plan.name

        return refund_dict
