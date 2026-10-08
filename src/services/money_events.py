"""
Money events for product analytics (rext-control task 712, step C).

A subscription that starts, is paid for, is cancelled, expires, fails a payment or
is refunded is something no browser sees happen: Lemon Squeezy tells this backend,
in a webhook. Once that webhook's work is committed, one event goes to PostHog from
here, so the counts and the amounts are the ones the books have.

An event carries no identity: no user, no email, no order or subscription id.
Whether a person allows usage analytics is known only to their browser (the
dashboard's consent rule), so the backend can't tell, and it sends what needs
no answer: that a plan was started, paid for or ended, and for how much. Each event
has an id of its own derived from the webhook's and carries the webhook's own time,
so a retry is the same event again.

Nothing is sent unless POSTHOG_PROJECT_KEY is set (the project's public key, the
one the dashboard uses), and never for a sandbox (test mode) purchase. A failure
to send is logged and never reaches the webhook's own result.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.utils.logger import logger

DEFAULT_HOST = "https://eu.i.posthog.com"
SEND_TIMEOUT_SECONDS = 3.0

# Lemon Squeezy's event -> ours (the thing first, past tense, as the dashboard's).
_EVENT_NAMES = {
    "subscription_created": "subscription_started",
    # Every invoice that was paid, whatever it was for: `billing_reason` says whether it is
    # the first payment ("initial"), a renewal or a plan change's charge ("updated").
    "subscription_payment_success": "subscription_payment_succeeded",
    "subscription_cancelled": "subscription_cancelled",
    "subscription_expired": "subscription_expired",
    "subscription_payment_failed": "subscription_payment_failed",
    # Two kinds of refund, under two names: of an order (the first payment), and of a later
    # invoice (a renewal). A dashboard counts each kind by its own name.
    "order_refunded": "subscription_refunded",
    "subscription_payment_refunded": "subscription_payment_refunded",
}
# The webhooks that carry an invoice: it names its subscription, and no plan.
_INVOICE_EVENTS = frozenset(
    {
        "subscription_payment_success",
        "subscription_payment_failed",
        "subscription_payment_refunded",
    }
)
# An invoice for a plan change is paid while the subscription may still be on the plan
# being left: its own webhook can arrive first.
_PLAN_CHANGE = "updated"


def _amount(cents: Any) -> Optional[float]:
    """
    A Lemon Squeezy amount as the backend's own books read it (the orders, the refunds,
    the payment handler): hundredths, whatever the currency. An event's figure is then
    the one the books hold. Across currencies a chart adds up `amount_usd`, which the
    provider always gives in cents of a dollar.
    """
    if isinstance(cents, bool):
        return None
    try:
        return round(int(cents) / 100, 2)
    except (TypeError, ValueError):
        return None


def _plan_source(event_type: str, payload: Dict[str, Any]) -> Optional[tuple]:
    """
    Where a webhook's plan is read from, and the id to look for: the variant that was
    bought, where the webhook names it (a subscription's own, an order's first item's),
    or the subscription an invoice belongs to. None when the webhook names neither, or
    when the subscription held now can't be trusted to be on the plan the invoice means:
    a plan change's invoice, and a refund that doesn't say what its invoice was for.
    """
    data = payload.get("data") or {}
    attributes = data.get("attributes") or {}
    if event_type in _INVOICE_EVENTS:
        reason = attributes.get("billing_reason")
        unsure = not reason and event_type == "subscription_payment_refunded"
        if reason == _PLAN_CHANGE or unsure:
            return None
        found_by, value = "subscription", attributes.get("subscription_id")
    elif event_type.startswith("subscription_"):
        found_by, value = "variant", attributes.get("variant_id")
    elif event_type.startswith("order_"):
        item = attributes.get("first_order_item")
        found_by, value = "variant", item.get("variant_id") if isinstance(item, dict) else None
    else:
        return None
    return (found_by, str(value)) if value else None


def _plan_query(found_by: str, value: str) -> Any:
    """
    The read that names a plan and tells its billing period. By the variant bought, it
    is the plan as it was sold: a later plan change doesn't relabel an order's refund.
    """
    if found_by == "variant":
        return (
            select(SubscriptionPlan.name, SubscriptionPlan.lemonsqueezy_variant_id_yearly)
            .where(
                or_(
                    SubscriptionPlan.lemonsqueezy_variant_id_monthly == value,
                    SubscriptionPlan.lemonsqueezy_variant_id_yearly == value,
                )
            )
            .limit(1)
        )
    return (
        select(SubscriptionPlan.name, UserSubscription.billing_period)
        .join(SubscriptionPlan, SubscriptionPlan.id == UserSubscription.plan_id)
        .where(UserSubscription.lemonsqueezy_subscription_id == value)
        .order_by(UserSubscription.created_at.desc())
        .limit(1)
    )


def money_event(
    event_type: str, payload: Dict[str, Any], held: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    The analytics event for one webhook, or None when it has none.

    Reads a short list of fields and nothing else: what plan, in what state, how
    much, in what currency. Never who. `held` is what the backend's own subscription
    says (`plan`, `billing_period`), where there is one: an invoice names no plan.
    """
    meta = payload.get("meta") or {}
    attributes = (payload.get("data") or {}).get("attributes") or {}
    if meta.get("test_mode") or attributes.get("test_mode"):
        return None

    name = _EVENT_NAMES.get(event_type)
    if name is None:
        return None

    # A subscription names its product and variant itself; an order keeps them on its
    # first item; an invoice has neither.
    item = attributes.get("first_order_item")
    named = {**(item if isinstance(item, dict) else {}), **attributes}
    properties: Dict[str, Any] = {}
    for ours, theirs in (
        ("product", "product_name"),
        ("variant", "variant_name"),
        ("status", "status"),
        ("currency", "currency"),
        ("billing_reason", "billing_reason"),
    ):
        value = named.get(theirs)
        if isinstance(value, str) and value:
            properties[ours] = value
    # The plan under the backend's own name for it, as every other event of the app's has it.
    for ours in ("plan", "billing_period"):
        value = (held or {}).get(ours)
        if isinstance(value, str) and value:
            properties[ours] = value

    amount = _amount(attributes.get("total"))
    if amount is not None and "total" in attributes:
        properties["amount"] = amount
        # The same amount in one currency for every event, so a chart can add them up.
        in_usd = _amount(attributes.get("total_usd"))
        if in_usd is not None and "total_usd" in attributes:
            properties["amount_usd"] = in_usd
    # Lemon Squeezy gives what has been refunded so far, not what this refund returned: a
    # second partial refund repeats the first one's amount inside its own. Sent under a name
    # that says so, with whether everything is back; never to be added up across events.
    refunded = _amount(attributes.get("refunded_amount"))
    if refunded is not None and attributes.get("refunded_amount"):
        properties["refunded_total"] = refunded
        if amount is not None and "total" in attributes:
            properties["full_refund"] = refunded >= amount
    elif attributes.get("refunded") and attributes.get("status") == "refunded":
        # A payload can leave the amount out; a status of "refunded" still says all of it came back.
        properties["full_refund"] = True
    return {"event": name, "properties": properties}


def _event_uuid(key: str) -> str:
    """The same thing that happened is the same event, however often it is sent."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"rext-server-event:{key}"))


def _environment() -> str:
    """Which deploy this is, as every event says it: production, staging or development."""
    return (os.getenv("ENVIRONMENT") or "development").lower()


async def send_server_event(
    event: str,
    properties: Dict[str, Any],
    *,
    key: str,
    occurred_at: Optional[datetime],
    person_id: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """
    Send one event from the backend to PostHog. True when it was taken; never raises.

    For every server-side event, not only the money ones. Call it after the work is
    committed. `key` names the thing that happened (a webhook's id, a run's id, a
    ledger row's id): the event's own id is made from it. `occurred_at` is when it
    happened, read once where it happened (the row's own time, never the moment of
    sending): PostHog keeps one of two deliveries only when their id and their time
    are both the same, so with both a retry is the same event again. It has to be
    given; None is for a thing with no time of its own, and such an event must not
    be retried. `person_id` is the account's id, and is given only when that person's
    answer on usage analytics allows it; without it the event is anonymous and no
    person is made for it. Every event says it is the app's, from the server, and
    which deploy.
    Never put an email, a name, a keyword, a title or any typed or generated text in
    `properties`.
    """
    api_key = os.getenv("POSTHOG_PROJECT_KEY")
    if not api_key:
        return False
    try:
        event_uuid = _event_uuid(f"{event}:{key}")
        body: Dict[str, Any] = {
            "api_key": api_key,
            "event": event,
            "distinct_id": person_id or event_uuid,
            "uuid": event_uuid,
            "properties": {
                **properties,
                "surface": "app",
                "source": "server",
                "environment": _environment(),
            },
        }
        if not person_id:
            # No person is made or updated for it.
            body["properties"]["$process_person_profile"] = False
        if occurred_at is not None:
            body["timestamp"] = occurred_at.isoformat()
        host = (os.getenv("POSTHOG_HOST") or DEFAULT_HOST).rstrip("/")
        if client is not None:
            # A borrowed client keeps its own settings for everything but the wait.
            response = await client.post(f"{host}/i/v0/e/", json=body, timeout=SEND_TIMEOUT_SECONDS)
        else:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as own:
                response = await own.post(f"{host}/i/v0/e/", json=body)
        # A redirect isn't followed, so it is no more "taken" than a refusal.
        if not 200 <= response.status_code < 300:
            logger.warning(
                "Server event not accepted",
                extra={"event": event, "key": key, "status": response.status_code},
            )
            return False
        # Over the project's quota PostHog still answers 200, and says so in the body.
        try:
            limited = response.json().get("quota_limited")
        except Exception:  # noqa: BLE001 - an answer that isn't JSON says nothing about quota
            limited = None
        if limited:
            logger.warning(
                "Server event dropped: the analytics project is over its quota",
                extra={"event": event, "key": key},
            )
            return False
        return True
    except Exception as error:  # noqa: BLE001 - analytics never fails the work it reports
        logger.warning(
            "Server event not sent",
            extra={"event": event, "key": key, "error": type(error).__name__},
        )
        return False


async def send_money_event(
    event_id: str,
    event_type: str,
    payload: Dict[str, Any],
    occurred_at: Optional[datetime] = None,
    client: Optional[httpx.AsyncClient] = None,
    held: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send one webhook's event, anonymous. True when PostHog took it; never raises."""
    if not os.getenv("POSTHOG_PROJECT_KEY"):
        return False
    try:
        event = money_event(event_type, payload, held)
    except Exception as error:  # noqa: BLE001 - analytics never fails a webhook
        logger.warning(
            "Money event not read",
            extra={"event_id": event_id, "error": type(error).__name__},
        )
        return False
    if event is None:
        return False
    return await send_server_event(
        event["event"],
        event["properties"],
        key=event_id,
        occurred_at=occurred_at,
        client=client,
    )


async def _held_plan(
    db: AsyncSession, event_type: str, payload: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    The plan and billing period a webhook is about, under the backend's own name for the
    plan: from the variant the webhook names, or for an invoice from the subscription
    held now. None when neither can say, and the event then goes without a plan.
    """
    source = _plan_source(event_type, payload)
    if source is None:
        return None
    found_by, value = source
    try:
        row = (await db.execute(_plan_query(found_by, value))).first()
    except Exception as error:  # noqa: BLE001 - analytics never fails a webhook
        logger.warning("Money event's plan not read", extra={"error": type(error).__name__})
        try:
            # The caller's session goes on being used: a failed read must not leave it broken.
            await db.rollback()
        except Exception:  # noqa: BLE001 - nothing more to do for it here
            pass
        return None
    if row is None:
        return None
    if found_by == "variant":
        yearly = str(row.lemonsqueezy_variant_id_yearly or "") == value
        return {"plan": row.name, "billing_period": "yearly" if yearly else "monthly"}
    period = getattr(row.billing_period, "value", row.billing_period)
    return {"plan": row.name, "billing_period": period}


async def record_money_event(db: AsyncSession, event_id: Optional[str]) -> bool:
    """
    Send the event for a webhook whose work has just been committed.

    Called after the commit, so an event is never sent for work that was rolled
    back. Reads the stored webhook, and nothing when analytics isn't configured.
    """
    if not event_id or not os.getenv("POSTHOG_PROJECT_KEY"):
        return False
    try:
        row = (
            await db.execute(
                select(
                    WebhookEvent.event_name, WebhookEvent.payload, WebhookEvent.created_at
                ).where(WebhookEvent.event_id == event_id)
            )
        ).first()
    except Exception as error:  # noqa: BLE001 - analytics never fails a webhook
        logger.warning(
            "Money event not read",
            extra={"event_id": event_id, "error": type(error).__name__},
        )
        return False
    if row is None or not isinstance(row.payload, dict):
        return False
    event_name, payload, created_at = row.event_name, row.payload, row.created_at
    if event_name not in _EVENT_NAMES:
        return False
    held = await _held_plan(db, event_name, payload)
    return await send_money_event(str(event_id), event_name, payload, created_at, held=held)
