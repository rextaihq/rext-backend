"""Order recording service.

Keeps the local `orders` table in step with LemonSqueezy. Every write is an
upsert keyed on `lemonsqueezy_order_id`, because LemonSqueezy retries webhooks
and the same order can arrive several times.

LemonSqueezy raises an order for every charge — the first purchase and each
subscription renewal alike — so `order_created` alone is enough to build a
complete billing history.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.orders import Order, OrderStatus
from src.utils.logger import logger

# LemonSqueezy order status -> our enum. Anything unrecognised stays PENDING.
_STATUS_MAP = {
    "pending": OrderStatus.PENDING,
    "paid": OrderStatus.PAID,
    "failed": OrderStatus.FAILED,
    "refunded": OrderStatus.REFUNDED,
    "partial_refund": OrderStatus.PARTIAL_REFUND,
}


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse a LemonSqueezy ISO 8601 timestamp, tolerating None and junk."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        # LemonSqueezy sends "2026-09-03T12:00:00.000000Z"
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        logger.warning(f"Could not parse order timestamp: {value!r}")
        return None


def order_to_invoice_dict(
    order: Order,
    customer_email: Optional[str] = None,
    customer_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Render a local order in the invoice shape the billing UI already reads.

    Amounts are stored in cents (as LemonSqueezy reports them) and exposed in
    major units here, matching the provider's own invoice mapping.

    The orders table holds no customer identity, so the caller passes the
    identity it already has (the authenticated user, who is the purchaser).
    """
    raw_status = (
        order.status.value if hasattr(order.status, "value") else str(order.status or "pending")
    )

    # An invoice records money received, and for a refunded order that payment
    # still happened. A refund is a separate credit line (see the invoice list,
    # which emits one per refund), not a retroactive edit of the original
    # invoice — so a refunded or partially refunded purchase keeps reading
    # "paid" and keeps its paid date. Marking it refunded here also blanked
    # `paid_at`, leaving the purchase looking as though it was never paid.
    # The order's refund state belongs on the purchase row, which shows the
    # refunded and still-refundable amounts.
    paid = raw_status in ("paid", "refunded", "partial_refund")
    status = "paid" if paid else raw_status

    return {
        "invoice_id": order.lemonsqueezy_order_id,
        "invoice_number": order.lemonsqueezy_order_id,
        "subscription_id": str(order.subscription_id) if order.subscription_id else None,
        "status": status,
        "amount": (order.total or 0) / 100.0,
        "subtotal": (order.subtotal or 0) / 100.0,
        "tax": (order.tax or 0) / 100.0,
        "currency": order.currency or "USD",
        "invoice_url": order.receipt_url,
        "invoice_date": order.ordered_at or order.created_at,
        "due_date": None,
        "paid_at": order.ordered_at if paid else None,
        "customer_email": customer_email,
        "customer_name": customer_name,
        "items": [],
    }


def refundable_amount(order: Order, refunded_total: int) -> int:
    """Cents still refundable against an order.

    The single definition of "remaining refundable" — every caller that decides
    whether a refund is allowed, and every response that shows the number to a
    human, goes through this so the UI can never offer what the API refuses.
    """
    return max(0, (order.total or 0) - max(0, refunded_total))


def apply_refund_state(
    order: Order,
    refunded_total: int,
    refunded_at: Optional[datetime] = None,
) -> None:
    """Set an order's status from how much of it has been refunded.

    Derived from the totals rather than from whichever refund happened to
    arrive last, so replayed or out-of-order webhooks cannot leave an order
    marked fully refunded when it still has a balance.
    """
    if refunded_total <= 0:
        return

    order.status = (
        OrderStatus.REFUNDED
        if refundable_amount(order, refunded_total) <= 0
        else OrderStatus.PARTIAL_REFUND
    )
    order.refunded_at = refunded_at or order.refunded_at or datetime.now(timezone.utc)
    order.updated_at = datetime.now(timezone.utc)


def map_order_status(status: Optional[str]) -> OrderStatus:
    """Map a LemonSqueezy order status string onto :class:`OrderStatus`."""
    return _STATUS_MAP.get((status or "").lower(), OrderStatus.PENDING)


class OrderService:
    """Read and write the local record of LemonSqueezy orders."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_lemonsqueezy_id(self, lemonsqueezy_order_id: str) -> Optional[Order]:
        """Return the order for a LemonSqueezy order id, if we have it."""
        if not lemonsqueezy_order_id:
            return None

        result = await self.db.execute(
            select(Order).where(Order.lemonsqueezy_order_id == str(lemonsqueezy_order_id))
        )
        return result.scalar_one_or_none()

    async def is_latest_order(self, user_id: UUID, lemonsqueezy_order_id: str) -> bool:
        """Whether this is the most recent charge on the account.

        LemonSqueezy raises an order for every charge, so the newest one is
        the charge that paid for the period the user is currently in. Callers
        reconciling an entitlement against a refund need this: credits reset
        to the full plan amount at each renewal and never roll over, so an
        older order no longer funds any balance the user still holds.

        Args:
            user_id: Owner of the orders.
            lemonsqueezy_order_id: The order to test.

        Returns:
            True if that order is the account's newest.
        """
        if not lemonsqueezy_order_id:
            return False

        result = await self.db.execute(
            select(Order.lemonsqueezy_order_id)
            .where(Order.user_id == user_id)
            .order_by(
                # `ordered_at` comes from LemonSqueezy and is the real charge
                # time; rows recorded before it was captured fall back to when
                # we wrote them.
                nullslast(Order.ordered_at.desc()),
                Order.created_at.desc(),
            )
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        return latest is not None and str(latest) == str(lemonsqueezy_order_id)

    async def record_order(
        self,
        *,
        user_id: UUID,
        order_data: Dict[str, Any],
        subscription_id: Optional[UUID] = None,
        lemonsqueezy_subscription_id: Optional[str] = None,
        receipt_url: Optional[str] = None,
    ) -> Optional[Order]:
        """Create or update the local record of a LemonSqueezy order.

        Args:
            user_id: Local user the order belongs to.
            order_data: Output of ``extract_order_data``.
            subscription_id: Local subscription, for orders raised by one.
            lemonsqueezy_subscription_id: LemonSqueezy subscription id, if any.
            receipt_url: Overrides the receipt URL carried in ``order_data``.

        Returns:
            The stored order, or None if the payload carried no order id.
        """
        lemonsqueezy_order_id = order_data.get("order_id")
        if not lemonsqueezy_order_id:
            logger.warning("Cannot record order: payload has no order id")
            return None

        lemonsqueezy_order_id = str(lemonsqueezy_order_id)
        status = map_order_status(order_data.get("status"))

        # LemonSqueezy reports a refund via a boolean as well as the status.
        if order_data.get("refunded") and status is not OrderStatus.PARTIAL_REFUND:
            status = OrderStatus.REFUNDED

        fields = {
            "user_id": user_id,
            "subscription_id": subscription_id,
            "lemonsqueezy_customer_id": order_data.get("customer_id") or None,
            "lemonsqueezy_subscription_id": lemonsqueezy_subscription_id,
            "lemonsqueezy_product_id": order_data.get("product_id") or None,
            "lemonsqueezy_variant_id": order_data.get("variant_id") or None,
            "product_name": order_data.get("product_name") or None,
            "total": order_data.get("total") or 0,
            "subtotal": order_data.get("subtotal"),
            "tax": order_data.get("tax"),
            "currency": order_data.get("currency") or "USD",
            "status": status,
            # Defaults from the payload so a caller cannot silently drop it.
            "receipt_url": receipt_url or order_data.get("receipt_url"),
            "refunded_at": _parse_datetime(order_data.get("refunded_at")),
            "ordered_at": _parse_datetime(order_data.get("created_at")),
        }

        order = await self.get_by_lemonsqueezy_id(lemonsqueezy_order_id)

        if order:
            # Webhook retry or a later event (e.g. a refund) for a known order.
            # Only overwrite with values we actually received, so a refund
            # webhook cannot blank out details the original order carried.
            for key, value in fields.items():
                if value is not None:
                    setattr(order, key, value)
            order.updated_at = datetime.now(timezone.utc)
            await self.db.flush()

            logger.info(
                f"Updated order {order.id} from LemonSqueezy order {lemonsqueezy_order_id}",
                extra={"order_id": str(order.id), "status": status.value},
            )
            return order

        order = Order(
            lemonsqueezy_order_id=lemonsqueezy_order_id,
            **fields,
        )
        self.db.add(order)
        await self.db.flush()

        logger.info(
            f"Recorded order {order.id} from LemonSqueezy order {lemonsqueezy_order_id}",
            extra={
                "order_id": str(order.id),
                "user_id": str(user_id),
                "status": status.value,
            },
        )
        return order
