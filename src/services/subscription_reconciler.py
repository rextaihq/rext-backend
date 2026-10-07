"""
The nightly reconciler: every unfinished Lemon Squeezy subscription re-read from its API.

Lemon Squeezy sends a webhook again only three times, so a state change can be
missed for good (F11, revnix/rext-control#336). Each night every subscription
that hasn't expired is read back from the API and applied with the webhook
handlers' own rules (handle_subscription_updated: the status decides access, an
older state than the stored one is ignored), and the emails those rules call for
(an unpaid subscription, say) are returned for sending once committed.
"""

import asyncio
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.providers.payment.provider_factory import get_payment_provider_singleton
from src.services.webhook_handlers.subscription_handlers import handle_subscription_updated
from src.utils.logger import logger

# Lemon Squeezy allows 300 API requests a minute; stay well under it.
_PAUSE_BETWEEN_READS_SECONDS = 0.25


async def reconcile_subscriptions(
    db: AsyncSession, provider=None, limit: int = 2000
) -> Dict[str, Any]:
    """Re-read and apply every unfinished subscription. Returns counts and emails to send."""
    rows = (
        await db.scalars(
            select(UserSubscription)
            .where(
                UserSubscription.lemonsqueezy_subscription_id.is_not(None),
                UserSubscription.status != SubscriptionStatus.EXPIRED,
                # Settled duplicates end here (duplicate_subscriptions.py), and are left out
                # before the limit: skipped afterwards, they would fill every batch for good.
                or_(
                    UserSubscription.subscription_metadata.is_(None),
                    ~UserSubscription.subscription_metadata.has_key("duplicate_of"),
                ),
            )
            .order_by(UserSubscription.updated_at.asc())
            .limit(limit)
        )
    ).all()
    provider = provider or (get_payment_provider_singleton() if rows else None)

    counts = {"checked": 0, "changed": 0, "failed": 0}
    emails: List[Dict[str, Any]] = []
    for row in rows:
        ls_id = row.lemonsqueezy_subscription_id
        before = row.status
        try:
            attributes = await provider.get_subscription_attributes(ls_id)
            result = await handle_subscription_updated(
                _as_webhook(ls_id, attributes), _ReconcileEvent(ls_id), db
            )
        except Exception as e:
            counts["failed"] += 1
            logger.warning(
                "Reconcile: could not re-read a subscription",
                extra={"lemonsqueezy_subscription_id": ls_id, "error": str(e)},
            )
            continue
        finally:
            # Every read is paced, a failed one too: errors back to back would hit the limit.
            await _pause()
        counts["checked"] += 1
        if row.status != before:
            counts["changed"] += 1
            logger.info(
                "Reconcile: subscription corrected from Lemon Squeezy",
                extra={
                    "subscription_id": str(row.id),
                    "from": before.value,
                    "to": row.status.value,
                },
            )
        if result and result.get("send_email"):
            emails.append(result)

    return {**counts, "emails": emails}


async def _pause() -> None:
    await asyncio.sleep(_PAUSE_BETWEEN_READS_SECONDS)


def _as_webhook(ls_id: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
    """The subscription's API state in the shape of a subscription_updated webhook."""
    return {
        "event_id": f"reconcile:{ls_id}",
        "event_type": "subscription_updated",
        "data": {"type": "subscriptions", "id": ls_id, "attributes": attributes},
        "meta": {},
        "custom_data": {},
        "raw_payload": {},
    }


class _ReconcileEvent:
    """Stands in for the webhook_events row a real webhook would have."""

    def __init__(self, ls_id: str):
        self.id: Optional[str] = None
        self.event_id = f"reconcile:{ls_id}"
        self.event_name = "subscription_updated"
