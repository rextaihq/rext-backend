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
    "order_refunded": "subscription_refunded",
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
    refunded = _amount(attributes.get("refunded_amount"))
    if refunded is not None and attributes.get("refunded_amount"):
        properties["refunded_amount"] = refunded
    return {"event": name, "properties": properties}


def _event_uuid(event_id: str) -> str:
    """The same webhook is the same event, however often it is sent."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"rext-money-event:{event_id}"))


async def send_money_event(
    event_id: str,
    event_type: str,
    payload: Dict[str, Any],
    occurred_at: Optional[datetime] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """Send one webhook's event. True when PostHog took it; never raises."""
    key = os.getenv("POSTHOG_PROJECT_KEY")
    if not key:
        return False
    try:
        event = money_event(event_type, payload)
        if event is None:
            return False
        anonymous_id = _event_uuid(event_id)
        body = {
            "api_key": key,
            "event": event["event"],
            "distinct_id": anonymous_id,
            "uuid": anonymous_id,
            "properties": {
                **event["properties"],
                "source": "backend",
                # No person is made or updated for it.
                "$process_person_profile": False,
            },
        }
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
                "Money event not accepted",
                extra={"event_id": event_id, "status": response.status_code},
            )
            return False
        return True
    except Exception as error:  # noqa: BLE001 - analytics never fails a webhook
        logger.warning(
            "Money event not sent",
            extra={"event_id": event_id, "error": type(error).__name__},
        )
        return False


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
