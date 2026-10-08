"""
Money events for product analytics (rext-control task 712, step C).

A subscription that starts, renews, is cancelled, expires, fails a payment or is
refunded is something no browser sees happen: Lemon Squeezy tells this backend, in
a webhook. Once that webhook's work is committed, one event goes to PostHog from
here, so the counts and the amounts are the ones the books have.

An event carries no identity: no user, no email, no order or subscription id.
Whether a person allows usage analytics is known only to their browser (the
dashboard's consent rule), so the backend can't tell, and it sends what needs
no answer: that a plan was started or ended, and for how much. Each event has an
id of its own derived from the webhook's, so a retry is the same event again.

Nothing is sent unless POSTHOG_PROJECT_KEY is set (the project's public key, the
one the dashboard uses), and never for a sandbox (test mode) purchase. A failure
to send is logged and never reaches the webhook's own result.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.webhooks import WebhookEvent
from src.utils.logger import logger

DEFAULT_HOST = "https://eu.i.posthog.com"
SEND_TIMEOUT_SECONDS = 3.0

# Lemon Squeezy's event -> ours (the thing first, past tense, as the dashboard's).
_EVENT_NAMES = {
    "subscription_created": "subscription_started",
    "subscription_cancelled": "subscription_cancelled",
    "subscription_expired": "subscription_expired",
    "subscription_payment_failed": "subscription_payment_failed",
    # Two kinds of refund, under two names: of an order (the first payment), and of a later
    # invoice (a renewal). A dashboard counts each kind by its own name.
    "order_refunded": "subscription_refunded",
    "subscription_payment_refunded": "subscription_payment_refunded",
}
# A payment that went through is a renewal only when Lemon Squeezy says so: the first
# payment is the start, and a charge for a plan change is neither.
_RENEWAL = "renewal"


def _amount(cents: Any) -> Optional[float]:
    """Lemon Squeezy's amounts are in cents; ours in the currency's unit."""
    try:
        return round(int(cents) / 100, 2)
    except (TypeError, ValueError):
        return None


def money_event(event_type: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    The analytics event for one webhook, or None when it has none.

    Reads a short list of fields and nothing else: what plan, in what state, how
    much, in what currency. Never who.
    """
    meta = payload.get("meta") or {}
    attributes = (payload.get("data") or {}).get("attributes") or {}
    if meta.get("test_mode") or attributes.get("test_mode"):
        return None

    if event_type == "subscription_payment_success":
        if attributes.get("billing_reason") != _RENEWAL:
            return None
        name = "subscription_renewed"
    else:
        name = _EVENT_NAMES.get(event_type)
        if name is None:
            return None

    properties: Dict[str, Any] = {}
    for ours, theirs in (
        ("plan", "variant_name"),
        ("product", "product_name"),
        ("status", "status"),
        ("currency", "currency"),
        ("billing_reason", "billing_reason"),
    ):
        value = attributes.get(theirs)
        if isinstance(value, str) and value:
            properties[ours] = value
    amount = _amount(attributes.get("total"))
    if amount is not None and "total" in attributes:
        properties["amount"] = amount
    # Lemon Squeezy gives what has been refunded so far, not what this refund returned: a
    # second partial refund repeats the first one's amount inside its own. Sent under a name
    # that says so, with whether everything is back; never to be added up across events.
    refunded = _amount(attributes.get("refunded_amount"))
    if refunded is not None and attributes.get("refunded_amount"):
        properties["refunded_total"] = refunded
        if amount is not None and "total" in attributes:
            properties["full_refund"] = refunded >= amount
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
    person_id: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """
    Send one event from the backend to PostHog. True when it was taken; never raises.

    For every server-side event, not only the money ones. Call it after the work is
    committed. `key` names the thing that happened (a webhook's id, a run's id, a
    ledger row's id): the event's own id is made from it, so a retry is the same event
    again. `person_id` is the account's id, and is given only when that person's answer
    on usage analytics allows it; without it the event is anonymous and no person is
    made for it. Every event says it is the app's, from the server, and which deploy.
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
            response = await client.post(f"{host}/i/v0/e/", json=body)
        else:
            async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as own:
                response = await own.post(f"{host}/i/v0/e/", json=body)
        if response.status_code >= 400:
            logger.warning(
                "Server event not accepted",
                extra={"event": event, "key": key, "status": response.status_code},
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
) -> bool:
    """Send one webhook's event, anonymous. True when PostHog took it; never raises."""
    if not os.getenv("POSTHOG_PROJECT_KEY"):
        return False
    try:
        event = money_event(event_type, payload)
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
    return await send_money_event(str(event_id), row.event_name, row.payload, row.created_at)
