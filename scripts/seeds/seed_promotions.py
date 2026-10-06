"""Seed the promotions: insert the ones missing (by code), never change an existing one.

A promotion is data: it is changed in the database (later, from the super admin),
not here. This seed runs on every environment, so a new database starts with the
promotions that already exist on stage and live.
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text

from scripts.seeds.base import get_seed_session

# The launch offer: a plan started in launch week gets double credits for its
# first month. The window is the one the marketing site's campaign bar counts
# down to (rext-site-v3, src/content/campaign.ts); the contract test in
# tests/contract keeps the two equal.
LAUNCH_PROMOTION = {
    "code": "launch-2026-10",
    "label": "Launch bonus",
    "kind": "bonus_credits",
    "credit_multiplier": 2,
    "bonus_credits": None,
    "starts_at": datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc),
    "ends_at": datetime(2026, 10, 14, 6, 59, tzinfo=timezone.utc),
    "plan_names": None,
    "billing_periods": None,
    "max_redemptions": None,
    "is_active": True,
}

PROMOTIONS = [LAUNCH_PROMOTION]

INSERT = text(
    "INSERT INTO promotions (id, code, label, kind, credit_multiplier, bonus_credits, "
    "starts_at, ends_at, plan_names, billing_periods, max_redemptions, is_active) "
    "VALUES (:id, :code, :label, :kind, :credit_multiplier, :bonus_credits, "
    ":starts_at, :ends_at, :plan_names, :billing_periods, :max_redemptions, :is_active)"
)


async def seed_promotions():
    """Insert the promotions that do not exist yet (by code)."""
    async with get_seed_session() as session:
        created = 0
        for promotion in PROMOTIONS:
            exists = await session.scalar(
                text("SELECT 1 FROM promotions WHERE code = :code"), {"code": promotion["code"]}
            )
            if exists:
                continue
            await session.execute(INSERT, {**promotion, "id": uuid4()})
            created += 1
        print(f"Promotions: {created} created, {len(PROMOTIONS) - created} already existed")


if __name__ == "__main__":
    asyncio.run(seed_promotions())
