"""What a customer paid for changing plan, which a refund of their order doesn't give back (F22).

Lemon Squeezy charges a plan change as a subscription invoice (`billing_reason: updated`), not as
an order. The app's refunds work on orders: the customer's own request and the admin's refund
give back the first payment only. Until they cover these invoices too, the admin's refund
screens name them, so the person refunding can give that payment back in Lemon Squeezy's
dashboard as well.

Read from the webhook events already stored: `subscription_payment_success` says what was paid,
`subscription_payment_refunded` what Lemon Squeezy gave back since.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.orders import Order
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.utils.datetime_utils import parse_provider_datetime

PAID = "subscription_payment_success"
REFUNDED = "subscription_payment_refunded"
PLAN_CHANGE = "updated"


@dataclass(frozen=True)
class PlanChangeCharge:
    """One paid plan-change invoice. Amounts are in cents."""

    invoice_id: str
    amount: int
    refunded_amount: int
    currency: str
    paid_at: Optional[datetime]

    @property
    def outstanding_amount(self) -> int:
        return max(self.amount - self.refunded_amount, 0)

    def as_row(self) -> Dict[str, Any]:
        return {
            "invoice_id": self.invoice_id,
            "amount": self.amount,
            "refunded_amount": self.refunded_amount,
            "outstanding_amount": self.outstanding_amount,
            "currency": self.currency,
            "paid_at": self.paid_at,
        }


def _cents(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def charges_from_events(events: Iterable[tuple[str, dict]]) -> Dict[str, List[PlanChangeCharge]]:
    """Per subscription id: its plan-change invoices that still hold money, oldest first.

    `events` are (event name, stored payload), oldest first. An invoice is a plan change's when
    one of its events says so; later events about the same invoice only update what was
    refunded, since a refund's event doesn't always repeat the reason.
    """
    invoices: Dict[str, dict] = {}
    for name, payload in events:
        data = (payload or {}).get("data") or {}
        attributes = data.get("attributes") or {}
        invoice_id = str(data.get("id") or "")
        subscription_id = str(attributes.get("subscription_id") or "")
        if not invoice_id or not subscription_id:
            continue
        invoice = invoices.setdefault(
            invoice_id,
            {"subscription_id": subscription_id, "plan_change": False, "paid": False},
        )
        if attributes.get("billing_reason") == PLAN_CHANGE:
            invoice["plan_change"] = True
        if name == PAID:
            invoice["paid"] = True
            invoice["amount"] = _cents(attributes.get("total"))
            invoice["currency"] = attributes.get("currency") or "USD"
            invoice["paid_at"] = parse_provider_datetime(
                attributes.get("created_at") or attributes.get("updated_at")
            )
        refunded = _cents(attributes.get("refunded_amount"))
        if name == REFUNDED and not refunded and attributes.get("status") == "refunded":
            # A full refund whose event names no amount.
            refunded = _cents(attributes.get("total"))
        invoice["refunded"] = max(invoice.get("refunded", 0), refunded)

    charges: Dict[str, List[PlanChangeCharge]] = {}
    for invoice_id, invoice in invoices.items():
        if not (invoice["plan_change"] and invoice["paid"]):
            continue
        charge = PlanChangeCharge(
            invoice_id=invoice_id,
            amount=invoice["amount"],
            refunded_amount=min(invoice["refunded"], invoice["amount"]),
            currency=invoice["currency"],
            paid_at=invoice["paid_at"],
        )
        if charge.outstanding_amount > 0:
            charges.setdefault(invoice["subscription_id"], []).append(charge)
    return charges


async def plan_change_charges(
    db: AsyncSession, subscription_ids: Sequence[Optional[str]]
) -> Dict[str, List[PlanChangeCharge]]:
    """`charges_from_events` for these Lemon Squeezy subscription ids, in one query."""
    ids = sorted({str(i) for i in subscription_ids if i})
    if not ids:
        return {}
    subscription_id = WebhookEvent.payload[("data", "attributes", "subscription_id")].astext
    result = await db.execute(
        select(WebhookEvent.event_name, WebhookEvent.payload)
        .where(WebhookEvent.event_name.in_((PAID, REFUNDED)), subscription_id.in_(ids))
        .order_by(WebhookEvent.created_at)
    )
    return charges_from_events((row[0], row[1]) for row in result.all())


async def plan_change_charges_for_orders(
    db: AsyncSession, orders: Sequence[Optional[Order]]
) -> Dict[str, List[PlanChangeCharge]]:
    """Per Lemon Squeezy order id: the plan-change charges of the subscription it started.

    An order made before the subscription's id was stored on it is matched through the
    subscription that names it as its first order.
    """
    by_order = {
        o.lemonsqueezy_order_id: o.lemonsqueezy_subscription_id
        for o in orders
        if o is not None and o.lemonsqueezy_order_id
    }
    unlinked = [order_id for order_id, subscription_id in by_order.items() if not subscription_id]
    if unlinked:
        result = await db.execute(
            select(
                UserSubscription.lemonsqueezy_order_id,
                UserSubscription.lemonsqueezy_subscription_id,
            ).where(
                UserSubscription.lemonsqueezy_order_id.in_(unlinked),
                UserSubscription.lemonsqueezy_subscription_id.is_not(None),
            )
        )
        by_order.update({row[0]: row[1] for row in result.all()})

    charges = await plan_change_charges(db, list(by_order.values()))
    return {
        order_id: charges[str(subscription_id)]
        for order_id, subscription_id in by_order.items()
        if subscription_id and str(subscription_id) in charges
    }
