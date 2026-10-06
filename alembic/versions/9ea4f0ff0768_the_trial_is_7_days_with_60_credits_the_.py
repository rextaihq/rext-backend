"""the trial is 7 days with 60 credits; the launch offer runs launch week

Revision ID: 9ea4f0ff0768
Revises: 897d94fe5747
Create Date: 2026-10-06 17:51:48.330609

Data only, for the release of 2026-10-07 (founder decisions on revnix/rext-control
#426 and #427):

- The trial plan gives 60 credits (it gave 50). Its length, 7 days, is in code
  (TRIAL_DURATION_DAYS). Only new trials change: a running trial keeps the end
  date and the credits it was given, so no subscription is touched here.
- The launch offer (promotion launch-2026-10) runs 2026-10-07 07:00 to
  2026-10-14 06:59 UTC. Live runs no seeds, so its promotions table is empty
  after its migrations: the row is inserted there, and only its window is set where
  the seed already made it.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ea4f0ff0768"
down_revision: Union[str, Sequence[str], None] = "897d94fe5747"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "UPDATE subscription_plans"
        " SET credits_per_month = 60, updated_at = now(),"
        " description = '7-day free trial. Test the full pipeline before committing.'"
        " WHERE name = 'trial' AND is_trial_plan"
    )
    op.execute(
        "INSERT INTO promotions (id, code, label, kind, credit_multiplier, starts_at, ends_at, is_active)"
        " VALUES (gen_random_uuid(), 'launch-2026-10', 'Launch bonus', 'bonus_credits', 2,"
        " TIMESTAMPTZ '2026-10-07 07:00:00+00', TIMESTAMPTZ '2026-10-14 06:59:00+00', true)"
        " ON CONFLICT (code) DO UPDATE"
        " SET starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at, updated_at = now()"
    )


def downgrade() -> None:
    """Downgrade schema.

    The trial back to 50 credits and the launch row back to the seed's old window;
    a row this upgrade inserted stays, since a promotion that granted bonuses is
    referenced by their credit grants.
    """
    op.execute(
        "UPDATE subscription_plans"
        " SET credits_per_month = 50, updated_at = now(),"
        " description = '14-day free trial. Test the full pipeline before committing.'"
        " WHERE name = 'trial' AND is_trial_plan"
    )
    op.execute(
        "UPDATE promotions SET starts_at = TIMESTAMPTZ '2026-10-04 00:00:00+00',"
        " ends_at = TIMESTAMPTZ '2026-10-11 06:59:00+00', updated_at = now()"
        " WHERE code = 'launch-2026-10'"
    )
