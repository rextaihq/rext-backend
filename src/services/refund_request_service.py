"""Customer refund requests: create, list and review.

The eligibility rules live here rather than in the routes, so the user-facing
endpoint and the admin review path cannot drift apart on what counts as
refundable.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.api.models.subscription_models.orders import Order, OrderStatus
from src.api.models.subscription_models.refund_requests import (
    REFUND_REQUEST_WINDOW_DAYS,
    RefundRequest,
    RefundRequestStatus,
)
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.services.order_service import refundable_amount
from src.services.refund_service import RefundService
from src.utils.logger import logger
from src.utils.rbac_utils import SUPER_ADMIN_HIERARCHY_THRESHOLD


class RefundRequestError(Exception):
    """A refund request was refused. The message is safe to show the user."""


def _as_uuid(value) -> UUID:
    """Coerce an id to UUID.

    Route handlers pass `current_user["identity"]`, which is a string, while
    model columns hold `uuid.UUID`. SQLAlchemy coerces strings inside queries,
    but a plain Python `==` between the two is always False — which silently
    turned an ownership check into "order not found".
    """
    return value if isinstance(value, UUID) else UUID(str(value))


class RefundRequestService:
    """Create and review customer refund requests."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_refunded_total(self, lemonsqueezy_order_id: str) -> int:
        """Total already refunded against an order, in cents.

        Delegates to RefundService so requests are judged against exactly the
        number the refund endpoints enforce — notably excluding failed refunds,
        which returned no money and must not consume refundable balance.
        """
        return await RefundService(self.db).get_refunded_total(lemonsqueezy_order_id)

    async def _get_credit_usage_details(self, order: Order) -> Dict[str, Any]:
        """Calculate credit usage and monetary cap for an order's subscription.

        Returns:
            Dict with keys:
            - granted: Total credits granted for the period
            - used: Credits consumed so far
            - unused: Remaining unused credits
            - original_amount: Total order price in cents
            - max_partial_refund_cents: Max allowed partial refund in cents based on unused credits
        """
        from src.api.models.subscription_models.subscriptions import (
            subscription_grants_access,
        )

        subscription = None

        # First try the subscription the order is linked to.
        if order.subscription_id:
            result = await self.db.execute(
                select(UserSubscription)
                .options(joinedload(UserSubscription.plan))
                .where(UserSubscription.id == order.subscription_id)
            )
            candidate = result.unique().scalar_one_or_none()

            # Only use it if it still grants access. When a user re-subscribes,
            # the old subscription is cancelled (current_credits=0) while the
            # new active one holds the real balance. Blindly trusting the link
            # made a fresh subscriber look like they had used every credit.
            if candidate and candidate.status in ("ACTIVE", "TRIAL"):
                subscription = candidate
            elif candidate and candidate.end_date and candidate.end_date > datetime.now(timezone.utc):
                # Cancelled but still within the paid-through grace period.
                subscription = candidate

        # Fall back to the user's currently-active subscription.
        if subscription is None:
            result = await self.db.execute(
                select(UserSubscription)
                .options(joinedload(UserSubscription.plan))
                .where(
                    UserSubscription.user_id == order.user_id,
                    subscription_grants_access(),
                )
                .order_by(UserSubscription.start_date.desc())
                .limit(1)
            )
            subscription = result.unique().scalar_one_or_none()

        # Last resort: any subscription for this user (newest first).
        if subscription is None:
            result = await self.db.execute(
                select(UserSubscription)
                .options(joinedload(UserSubscription.plan))
                .where(UserSubscription.user_id == order.user_id)
                .order_by(UserSubscription.start_date.desc())
                .limit(1)
            )
            subscription = result.unique().scalar_one_or_none()

        original_amount = order.total or 0

        if not subscription or not subscription.plan:
            return {
                "granted": 0,
                "used": 0,
                "unused": 0,
                "original_amount": original_amount,
                "max_partial_refund_cents": original_amount,
            }

        plan = subscription.plan
        granted = plan.credits_per_month or 0

        if plan.is_trial_plan or granted <= 0:
            return {
                "granted": granted,
                "used": 0,
                "unused": 0,
                "original_amount": original_amount,
                "max_partial_refund_cents": original_amount,
            }

        meta = {**(subscription.subscription_metadata or {})}
        previous = meta.get("refund_credit_reduction") or {}
        already_cut = (
            int(previous.get("credits") or 0)
            if str(previous.get("order_id")) == str(order.lemonsqueezy_order_id)
            else 0
        )

        balance = subscription.current_credits or 0
        used = max(0, granted - balance - already_cut)
        unused = max(0, balance)
        max_partial_refund_cents = (unused * original_amount) // granted if granted > 0 else 0

        return {
            "granted": granted,
            "used": used,
            "unused": unused,
            "original_amount": original_amount,
            "max_partial_refund_cents": max_partial_refund_cents,
        }

    async def get_super_admin_ids(self) -> List[UUID]:
        """User ids of everyone who can review refund requests."""
        result = await self.db.execute(
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.hierarchy_level >= SUPER_ADMIN_HIERARCHY_THRESHOLD)
            .distinct()
        )
        return list(result.scalars().all())

    async def create_request(
        self,
        *,
        user_id: UUID,
        lemonsqueezy_order_id: str,
        reason: str,
        requested_amount: Optional[int] = None,
        enforce_window: bool = True,
    ) -> RefundRequest:
        """Raise a refund request against one of the user's own orders.

        Args:
            user_id: Owner of the order. An admin logging a request emailed in
                by a customer passes that customer's id, not their own.
            lemonsqueezy_order_id: The order being asked about.
            reason: Why the refund is wanted, in the customer's words.
            requested_amount: Cents to ask for, for a partial refund. Defaults
                to the order's whole remaining refundable balance.
            enforce_window: Whether the refund window applies. An admin logging
                a request that arrived by email passes False: the customer may
                well have written inside the window even if it has since
                lapsed, and the admin reviews the request either way.

        Raises:
            RefundRequestError: If the order is not eligible. The message is
                written for the customer.
        """
        user_id = _as_uuid(user_id)

        if not (reason or "").strip():
            raise RefundRequestError("Please tell us why you're requesting a refund.")

        result = await self.db.execute(
            select(Order).where(Order.lemonsqueezy_order_id == str(lemonsqueezy_order_id))
        )
        order = result.scalar_one_or_none()

        if not order:
            raise RefundRequestError("We couldn't find that order.")

        # Checked explicitly rather than filtering by user in the query above,
        # so someone probing another user's order id gets the same answer as
        # for a nonexistent one.
        if order.user_id != user_id:
            raise RefundRequestError("We couldn't find that order.")

        # A partially refunded order is still refundable for the balance, so
        # it stays requestable; only unpaid or fully refunded ones do not.
        if order.status not in (OrderStatus.PAID, OrderStatus.PARTIAL_REFUND):
            raise RefundRequestError(
                "Only paid orders can be refunded. This order is "
                f"{order.status.value if order.status else 'unknown'}."
            )

        placed_at = order.ordered_at or order.created_at
        if enforce_window and placed_at:
            if placed_at.tzinfo is None:
                placed_at = placed_at.replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(days=REFUND_REQUEST_WINDOW_DAYS)
            if placed_at < cutoff:
                raise RefundRequestError(
                    f"Refunds can only be requested within "
                    f"{REFUND_REQUEST_WINDOW_DAYS} days of purchase."
                )

        refunded_so_far = await self._get_refunded_total(order.lemonsqueezy_order_id)
        remaining = refundable_amount(order, refunded_so_far)
        if remaining <= 0:
            raise RefundRequestError("This order has already been fully refunded.")

        usage = await self._get_credit_usage_details(order)
        used_credits = usage["used"]
        granted_credits = usage["granted"]
        max_partial = usage["max_partial_refund_cents"]

        # Determine target refund amount
        target_amount = requested_amount or remaining

        if target_amount == remaining:
            # Full refund request: allowed ONLY if 50 credits or fewer consumed
            if granted_credits > 0 and used_credits > 50:
                msg = (
                    f"Full refunds are only available if 50 or fewer credits have been used "
                    f"(you have used {used_credits} credits)."
                )
                if max_partial > 0:
                    msg += f" You may request a partial refund up to {max_partial / 100:.2f} {order.currency or 'USD'}."
                else:
                    msg += " No partial refund is available for your remaining credits."
                raise RefundRequestError(msg)
        else:
            # Partial refund request
            if requested_amount <= 0:
                raise RefundRequestError("The refund amount must be more than zero.")
            if requested_amount > remaining:
                raise RefundRequestError(
                    f"Only {remaining / 100:.2f} {order.currency or 'USD'} is "
                    f"still refundable on this order."
                )
            if granted_credits > 0 and requested_amount > max_partial:
                raise RefundRequestError(
                    f"The maximum partial refund for your remaining {usage['unused']} unused credits "
                    f"is {max_partial / 100:.2f} {order.currency or 'USD'}."
                )

        # "Open" means the request still has somewhere to go: waiting to be
        # reviewed, or approved and waiting to be paid out. An approved request
        # that has already produced a refund is finished — it must not block a
        # fresh request against whatever balance the order has left, which is
        # exactly what happens after a partial refund.
        #
        # There is no separate "processing" status: a request is being paid out
        # when it is approved and its refund_id is still unset, and it is done
        # the moment that id exists.
        existing = await self.db.execute(
            select(RefundRequest)
            .where(
                RefundRequest.order_id == order.id,
                or_(
                    RefundRequest.status == RefundRequestStatus.PENDING,
                    and_(
                        RefundRequest.status == RefundRequestStatus.APPROVED,
                        RefundRequest.refund_id.is_(None),
                    ),
                ),
            )
            .limit(1)
        )
        if existing.scalars().first():
            raise RefundRequestError(
                "You already have an active refund request open for this order."
            )

        request = RefundRequest(
            user_id=user_id,
            order_id=order.id,
            lemonsqueezy_order_id=order.lemonsqueezy_order_id,
            # What was asked for, defaulting to everything still refundable —
            # which is the whole order until a partial refund has taken a bite
            # out of it.
            requested_amount=requested_amount or remaining,
            currency=order.currency or "USD",
            reason=reason.strip(),
            status=RefundRequestStatus.PENDING,
        )
        self.db.add(request)
        await self.db.flush()

        logger.info(
            f"Refund request {request.id} raised for order {order.lemonsqueezy_order_id}",
            extra={"user_id": str(user_id), "order_id": order.lemonsqueezy_order_id},
        )
        return request

    async def get(self, request_id: UUID) -> Optional[RefundRequest]:
        """Load one request with its user and order."""
        result = await self.db.execute(
            select(RefundRequest)
            .options(
                joinedload(RefundRequest.user),
                joinedload(RefundRequest.order),
            )
            .where(RefundRequest.id == request_id)
        )
        return result.unique().scalar_one_or_none()

    async def list_for_user(self, user_id) -> List[RefundRequest]:
        """A customer's own requests, newest first."""
        user_id = _as_uuid(user_id)
        result = await self.db.execute(
            select(RefundRequest)
            .where(RefundRequest.user_id == user_id)
            .order_by(RefundRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_for_admin(
        self,
        *,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """Requests for review, pending first so the queue is actionable."""
        base = select(RefundRequest).options(
            joinedload(RefundRequest.user),
            joinedload(RefundRequest.order),
        )

        if status:
            base = base.where(RefundRequest.status == status.lower())

        total_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total_items = total_result.scalar() or 0

        result = await self.db.execute(
            base.order_by(
                # Pending first regardless of age, then newest.
                (RefundRequest.status != RefundRequestStatus.PENDING),
                RefundRequest.created_at.desc(),
            )
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
        requests = list(result.unique().scalars().all())

        return {
            "requests": requests,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_items": total_items,
                "total_pages": (total_items + per_page - 1) // per_page,
            },
        }

    async def mark_reviewed(
        self,
        *,
        request: RefundRequest,
        admin_user_id: UUID,
        status: RefundRequestStatus,
        admin_note: Optional[str] = None,
        refund_id: Optional[UUID] = None,
    ) -> RefundRequest:
        """Record an admin's decision on a request."""
        request.status = status
        request.reviewed_by_user_id = _as_uuid(admin_user_id)
        request.admin_note = (admin_note or "").strip() or None
        request.reviewed_at = datetime.now(timezone.utc)
        request.refund_id = refund_id
        await self.db.flush()

        logger.info(
            f"Refund request {request.id} marked {status.value}",
            extra={
                "request_id": str(request.id),
                "admin_user_id": str(admin_user_id),
                "refund_id": str(refund_id) if refund_id else None,
            },
        )
        return request
