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
from datetime import datetime, timedelta, timezone
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
RENEWAL = "renewal"
# An order and the invoice of that same payment are stamped moments apart. A renewal's
# invoice this soon after an order is that order's own, not the start of the next period.
SAME_PAYMENT = timedelta(hours=1)


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


def _utc(moment: Optional[datetime]) -> Optional[datetime]:
    """The same moment with its zone said: the parsed provider times and some columns carry none."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=timezone.utc)


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
            invoice["paid_at"] = _utc(
                parse_provider_datetime(
                    attributes.get("created_at") or attributes.get("updated_at")
                )
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


def renewals_from_events(events: Iterable[tuple[str, dict]]) -> Dict[str, List[datetime]]:
    """Per subscription id: when each of its renewals was paid, oldest first.

    A renewal is a subscription invoice too, and no order is recorded for it: its payment
    is what starts the next period.
    """
    renewals: Dict[str, List[datetime]] = {}
    seen = set()
    for name, payload in events:
        data = (payload or {}).get("data") or {}
        attributes = data.get("attributes") or {}
        invoice_id = str(data.get("id") or "")
        subscription_id = str(attributes.get("subscription_id") or "")
        if name != PAID or attributes.get("billing_reason") != RENEWAL:
            continue
        if not invoice_id or not subscription_id or invoice_id in seen:
            continue
        paid_at = _utc(
            parse_provider_datetime(attributes.get("created_at") or attributes.get("updated_at"))
        )
        if paid_at is not None:
            seen.add(invoice_id)
            renewals.setdefault(subscription_id, []).append(paid_at)
    return {key: sorted(times) for key, times in renewals.items()}


async def _payment_events(
    db: AsyncSession, subscription_ids: Sequence[Optional[str]]
) -> List[tuple[str, dict]]:
    """The stored payment events of these Lemon Squeezy subscription ids, oldest first."""
    ids = sorted({str(i) for i in subscription_ids if i})
    if not ids:
        return []
    subscription_id = WebhookEvent.payload[("data", "attributes", "subscription_id")].astext
    result = await db.execute(
        select(WebhookEvent.event_name, WebhookEvent.payload)
        .where(WebhookEvent.event_name.in_((PAID, REFUNDED)), subscription_id.in_(ids))
        .order_by(WebhookEvent.created_at)
    )
    return [(row[0], row[1]) for row in result.all()]


async def plan_change_charges(
    db: AsyncSession, subscription_ids: Sequence[Optional[str]]
) -> Dict[str, List[PlanChangeCharge]]:
    """`charges_from_events` for these Lemon Squeezy subscription ids, in one query."""
    return charges_from_events(await _payment_events(db, subscription_ids))


def in_its_period(
    charges: Sequence[PlanChangeCharge],
    paid_at: Optional[datetime],
    other_payments: Sequence[datetime],
) -> List[PlanChangeCharge]:
    """The charges that belong to the payment made at `paid_at`: those paid from then until the
    subscription's next payment (`other_payments`: the times of the subscription's other orders
    and of its renewals).

    A plan change paid in an earlier period is that period's order's to answer for, not a later
    renewal's. A charge whose day is unknown goes with the newest payment; an order whose own
    time is unknown (none is, the column is required) can't be placed, so nothing is held back.
    """
    start = _utc(paid_at)
    after = sorted(t for t in (_utc(t) for t in other_payments) if start and t and t > start)
    end = after[0] if after else None
    kept = []
    for charge in charges:
        if charge.paid_at is None or start is None:
            if end is None:
                kept.append(charge)
        elif charge.paid_at >= start and (end is None or charge.paid_at < end):
            kept.append(charge)
    return kept


async def plan_change_charges_for_orders(
    db: AsyncSession, orders: Sequence[Optional[Order]]
) -> Dict[str, List[PlanChangeCharge]]:
    """Per Lemon Squeezy order id: the plan changes paid in the period that order paid for.

    An order made before the subscription's id was stored on it is matched through the
    subscription that names it as its first order. Its period ends at the subscription's
    next payment: another order's, or a renewal's, which is an invoice with no order of its
    own. A plan change paid after a renewal is that later period's, and is given back with
    the renewal's invoice in Lemon Squeezy, where both are listed.
    """
    asked = {
        o.lemonsqueezy_order_id: o for o in orders if o is not None and o.lemonsqueezy_order_id
    }
    by_order = {order_id: o.lemonsqueezy_subscription_id for order_id, o in asked.items()}
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

    events = await _payment_events(db, list(by_order.values()))
    charges = charges_from_events(events)
    if not charges:
        return {}
    renewals = renewals_from_events(events)

    # When each of those subscriptions was paid for, to tell one period from the next.
    payments: Dict[str, Dict[str, Optional[datetime]]] = {}
    result = await db.execute(
        select(
            Order.lemonsqueezy_subscription_id,
            Order.lemonsqueezy_order_id,
            Order.ordered_at,
            Order.created_at,
        ).where(Order.lemonsqueezy_subscription_id.in_(list(charges)))
    )
    for subscription_id, order_id, ordered_at, created_at in result.all():
        payments.setdefault(str(subscription_id), {})[order_id] = ordered_at or created_at
    for order_id, subscription_id in by_order.items():
        if subscription_id:
            order = asked[order_id]
            payments.setdefault(str(subscription_id), {}).setdefault(
                order_id, order.ordered_at or order.created_at
            )

    found: Dict[str, List[PlanChangeCharge]] = {}
    for order_id, subscription_id in by_order.items():
        key = str(subscription_id) if subscription_id else ""
        if key not in charges:
            continue
        times = payments[key]
        paid_at = _utc(times[order_id])
        others = [t for other, t in times.items() if other != order_id and t is not None]
        others += [
            renewed
            for renewed in renewals.get(key, [])
            if paid_at is None or renewed - paid_at > SAME_PAYMENT
        ]
        own = in_its_period(charges[key], paid_at, others)
        if own:
            found[order_id] = own
    return found
