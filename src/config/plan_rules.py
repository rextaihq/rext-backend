"""
The rules every plan shares, defined once.

Prices, credits and limits are per plan and live in the `subscription_plans`
table; the credits each pipeline stage costs live in
`src/utils/credit_manager.py`. What is left is here: how long the trial lasts
(applied at signup) and the offers on new subscriptions (announced by
`GET /api/v1/plans`).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Every new account starts on the trial plan for this many days.
TRIAL_DURATION_DAYS = 14


@dataclass(frozen=True)
class PlanOffer:
    """A time-boxed offer on subscriptions started inside its window."""

    id: str
    kind: str
    credit_multiplier: int
    starts_at: datetime
    ends_at: datetime
    # An offer is announced only once the backend grants it: until the webhook
    # handler applies the bonus credits, the dashboard must not promise them.
    granted: bool

    def is_active(self, now: datetime) -> bool:
        return self.granted and self.starts_at <= now < self.ends_at


# The launch offer: a plan started in launch week gets double credits for its
# first month. The window is the one the marketing site's campaign bar counts
# down to (rext-site-v3, src/content/campaign.ts); the contract test in
# tests/contract keeps the two equal.
LAUNCH_OFFER = PlanOffer(
    id="launch-2026-10",
    kind="first_month_credit_multiplier",
    credit_multiplier=2,
    starts_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
    ends_at=datetime(2026, 10, 11, 6, 59, tzinfo=timezone.utc),
    granted=False,
)

OFFERS: tuple[PlanOffer, ...] = (LAUNCH_OFFER,)


def active_offer(now: Optional[datetime] = None) -> Optional[PlanOffer]:
    """The offer a subscription started at `now` receives, if any."""
    now = now or datetime.now(timezone.utc)
    return next((offer for offer in OFFERS if offer.is_active(now)), None)
