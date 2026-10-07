"""
The nightly reconciler: every unfinished Lemon Squeezy subscription re-read from its API.

Lemon Squeezy sends a webhook again only three times, so a state change can be
missed for good (F11, revnix/rext-control#336). Each night every subscription
that hasn't expired is read back from the API and applied with the webhook
handlers' own rules (handle_subscription_updated: the status decides access, an
older state than the stored one is ignored), and the emails those rules call for
(an unpaid subscription, say) are returned for sending once committed.

Each subscription is its own short transaction (read, apply, commit), so no row
stays locked while the batch walks the others and a webhook never waits on it.
Every attempt is stamped (`reconciled_at` in the row's metadata) and the batch
takes the least recently tried first, so a subscription that always fails to
read goes to the back instead of filling every night's batch (#529).
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.subscriptions import (
    SubscriptionStatus,
    UserSubscription,
    not_a_known_duplicate,
)
from src.providers.payment.provider_factory import get_payment_provider_singleton
from src.services.duplicate_subscriptions import settle_duplicate_subscriptions
from src.services.webhook_handlers.subscription_handlers import (
    cancellation_email_task,
    handle_subscription_updated,
)
from src.utils.logger import logger

# Lemon Squeezy allows 300 API requests a minute; stay well under it.
_PAUSE_BETWEEN_READS_SECONDS = 0.25
# When the reconcile last tried a subscription, kept in the row's metadata.
_RECONCILED_AT = "reconciled_at"
_RUNNING = (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)


async def reconcile_subscriptions(
    db: AsyncSession, provider=None, limit: int = 2000
) -> Dict[str, Any]:
    """Re-read and apply every unfinished subscription. Returns counts and emails to send."""
    targets = (
        await db.execute(
            select(
                UserSubscription.id,
                UserSubscription.lemonsqueezy_subscription_id,
                UserSubscription.status,
                UserSubscription.user_id,
            )
            .where(
                UserSubscription.lemonsqueezy_subscription_id.is_not(None),
                UserSubscription.status != SubscriptionStatus.EXPIRED,
                # Known duplicates (settled here, or left to a person) are left out before
                # the limit: skipped afterwards, they would fill every batch for good.
                not_a_known_duplicate(),
            )
            .order_by(
                UserSubscription.subscription_metadata[_RECONCILED_AT].astext.asc().nulls_first(),
                UserSubscription.updated_at.asc(),
            )
            .limit(limit)
        )
    ).all()
    provider = provider or (get_payment_provider_singleton() if targets else None)

    counts = {"checked": 0, "changed": 0, "failed": 0}
    emails: List[Dict[str, Any]] = []
    for row_id, ls_id, before, user_id in targets:
        try:
            # A failure undoes only this subscription's half-applied changes.
            async with db.begin_nested():
                attributes = await provider.get_subscription_attributes(ls_id)
                result = await handle_subscription_updated(
                    _as_webhook(ls_id, attributes), _ReconcileEvent(ls_id), db
                )
                row = await db.get(UserSubscription, row_id)
                after = row.status
                if after != before and after in _RUNNING:
                    # A missed recovery can revive an older subscription the customer
                    # has since replaced: the duplicate check runs as after a webhook.
                    await settle_duplicate_subscriptions(db, user_id)
                if after == SubscriptionStatus.CANCELLED and before != after and not result:
                    # A missed subscription_cancelled: its email and notice, as the webhook's.
                    result = await cancellation_email_task(db, row)
        except Exception as e:
            counts["failed"] += 1
            logger.warning(
                "Reconcile: could not re-read a subscription",
                extra={"lemonsqueezy_subscription_id": ls_id, "error": str(e)},
            )
        else:
            counts["checked"] += 1
            if after != before:
                counts["changed"] += 1
                logger.info(
                    "Reconcile: subscription corrected from Lemon Squeezy",
                    extra={"subscription_id": str(row_id), "from": before.value, "to": after.value},
                )
            if result and result.get("send_email"):
                emails.append(result)
        finally:
            await _stamp_attempt(db, row_id)
            await db.commit()
            # Every read is paced, a failed one too: errors back to back would hit the limit.
            await _pause()

    return {**counts, "emails": emails}


async def _stamp_attempt(db: AsyncSession, row_id) -> None:
    row = await db.get(UserSubscription, row_id, populate_existing=True)
    if row is not None:
        row.subscription_metadata = {
            **(row.subscription_metadata or {}),
            _RECONCILED_AT: datetime.now(timezone.utc).isoformat(),
        }
        await db.flush()


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
