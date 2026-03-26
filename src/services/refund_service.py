"""
Refund Service

Handles refund operations including:
- Creating refunds via LemonSqueezy API
- Tracking refund history
- Processing refund webhooks
- Sending refund notifications
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, cast, Integer
from sqlalchemy.orm import joinedload

from src.api.models.subscription_models.refunds import Refund, RefundStatus
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.licenses import License, LicenseStatus
from src.api.models.user_models.users import Users
from src.utils.logger import logger
from src.services.webhook_monitoring_service import _mask_email


class RefundService:
    """Service for managing refunds."""

    def __init__(self, db: AsyncSession):
        """
        Initialize refund service.

        Args:
            db: Database session
        """
        self.db = db

    async def create_refund_record(
        self,
        user_id: UUID,
        lemonsqueezy_order_id: str,
        refund_amount: int,
        original_amount: int,
        subscription_id: Optional[UUID] = None,
        lemonsqueezy_refund_id: Optional[str] = None,
        reason: Optional[str] = None,
        currency: str = "USD",
    ) -> Refund:
        """
        Create a refund record in the database.

        Args:
            user_id: User receiving the refund
            lemonsqueezy_order_id: LemonSqueezy order ID
            refund_amount: Amount to refund in cents
            original_amount: Original order amount in cents
            subscription_id: Associated subscription (optional)
            lemonsqueezy_refund_id: LemonSqueezy refund ID (optional)
            reason: Refund reason
            currency: Currency code

        Returns:
            Refund: Created refund record
        """
        is_partial = refund_amount < original_amount

        refund = Refund(
            user_id=user_id,
            subscription_id=subscription_id,
            lemonsqueezy_order_id=lemonsqueezy_order_id,
            lemonsqueezy_refund_id=lemonsqueezy_refund_id,
            refund_amount=refund_amount,
            original_amount=original_amount,
            currency=currency,
            reason=reason,
            status=RefundStatus.PENDING,
            is_partial=is_partial,
        )

        self.db.add(refund)
        await self.db.flush()

        logger.info(
            f"Created refund record {refund.id} for order {lemonsqueezy_order_id}",
            extra={
                "refund_id": str(refund.id),
                "order_id": lemonsqueezy_order_id,
                "amount": refund_amount,
                "is_partial": is_partial
            }
        )

        return refund

    async def mark_refund_completed(
        self,
        refund_id: UUID,
        lemonsqueezy_refund_id: Optional[str] = None
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

        logger.info(
            f"Marked refund {refund_id} as completed",
            extra={"refund_id": str(refund_id)}
        )

        return refund

    async def mark_refund_failed(
        self,
        refund_id: UUID,
        reason: Optional[str] = None
    ) -> Refund:
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
            extra={"refund_id": str(refund_id), "reason": reason}
        )

        return refund

    async def get_refund_by_order_id(
        self,
        lemonsqueezy_order_id: str
    ) -> Optional[Refund]:
        """
        Get refund by LemonSqueezy order ID.

        Args:
            lemonsqueezy_order_id: LemonSqueezy order ID

        Returns:
            Refund or None
        """
        stmt = select(Refund).where(
            Refund.lemonsqueezy_order_id == lemonsqueezy_order_id
        ).order_by(desc(Refund.created_at))

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

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
                joinedload(Refund.subscription).joinedload(UserSubscription.plan)
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
            func.sum(
                cast(Refund.status == RefundStatus.COMPLETED, Integer)
            ).label("completed_count"),
            func.sum(
                cast(Refund.status == RefundStatus.PENDING, Integer)
            ).label("pending_count"),
            func.sum(
                cast(Refund.status == RefundStatus.FAILED, Integer)
            ).label("failed_count"),
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
                refund_dict["user_email_masked"] = _mask_email(refund.user.email)
                refund_dict["user_name"] = refund.user.full_name or refund.user.display_name or "***"

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
                joinedload(Refund.subscription).joinedload(UserSubscription.plan)
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
            refund_dict["user_email_masked"] = _mask_email(refund.user.email)
            refund_dict["user_name"] = refund.user.full_name or refund.user.display_name or "***"

        # Add plan details
        if refund.subscription and refund.subscription.plan:
            refund_dict["plan_name"] = refund.subscription.plan.name

        return refund_dict

    async def process_refund_webhook(
        self,
        lemonsqueezy_order_id: str,
        refund_amount: int,
        original_amount: int,
        reason: Optional[str] = None,
    ) -> Refund:
        """
        Process a refund from webhook data.

        Creates a refund record, updates license/subscription status.

        Args:
            lemonsqueezy_order_id: LemonSqueezy order ID
            refund_amount: Refund amount in cents
            original_amount: Original amount in cents
            reason: Refund reason

        Returns:
            Refund: Created/updated refund record
        """
        # Check if refund already exists
        existing_refund = await self.get_refund_by_order_id(lemonsqueezy_order_id)
        if existing_refund:
            logger.info(f"Refund already exists for order {lemonsqueezy_order_id}")
            return existing_refund

        # Find license by order ID
        license_stmt = select(License).where(
            License.lemonsqueezy_order_id == lemonsqueezy_order_id
        )
        license_result = await self.db.execute(license_stmt)
        license_record = license_result.scalar_one_or_none()

        # Find subscription by order ID
        subscription_stmt = select(UserSubscription).where(
            UserSubscription.lemonsqueezy_order_id == lemonsqueezy_order_id
        )
        subscription_result = await self.db.execute(subscription_stmt)
        subscription = subscription_result.scalar_one_or_none()

        if not license_record and not subscription:
            logger.warning(f"No license or subscription found for refunded order {lemonsqueezy_order_id}")
            # Try to find user by order (this might fail, but we'll handle it)
            raise ValueError(f"Cannot process refund: No license or subscription found for order {lemonsqueezy_order_id}")

        user_id = license_record.user_id if license_record else subscription.user_id
        subscription_id = subscription.id if subscription else None

        # Create refund record
        refund = await self.create_refund_record(
            user_id=user_id,
            lemonsqueezy_order_id=lemonsqueezy_order_id,
            refund_amount=refund_amount,
            original_amount=original_amount,
            subscription_id=subscription_id,
            reason=reason,
        )

        # Mark as completed immediately since webhook already processed
        await self.mark_refund_completed(refund.id)

        return refund
