"""the launch offer runs from 8 to 15 October

Revision ID: 3d51938f0c7e
Revises: 9ea4f0ff0768
Create Date: 2026-10-06 23:18:55.707423

Data only. The launch moved to 2026-10-08 (founder, 2026-10-06, revnix/rext-control
#427 and #439), so the launch offer (promotion launch-2026-10, double credits on a
first payment) runs 2026-10-08 07:00 to 2026-10-15 06:59 UTC, on the same terms.
9ea4f0ff0768 set the earlier window and is applied already, so this one moves it.
The row is inserted where it's missing, as there, and otherwise only its window
changes.
"""

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d51938f0c7e"
down_revision: Union[str, Sequence[str], None] = "9ea4f0ff0768"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The window, equal to scripts/seeds/seed_promotions.py (test_plan_catalog checks it).
STARTS_AT = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)
ENDS_AT = datetime(2026, 10, 15, 6, 59, tzinfo=timezone.utc)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            "INSERT INTO promotions (id, code, label, kind, credit_multiplier, starts_at, ends_at,"
            " is_active)"
            " VALUES (gen_random_uuid(), 'launch-2026-10', 'Launch bonus', 'bonus_credits', 2,"
            " :starts_at, :ends_at, true)"
            " ON CONFLICT (code) DO UPDATE"
            " SET starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at, updated_at = now()"
        ).bindparams(starts_at=STARTS_AT, ends_at=ENDS_AT)
    )


def downgrade() -> None:
    """Downgrade schema.

    The window back to 9ea4f0ff0768's; the row stays, since credit grants refer to it.
    """
    op.execute(
        "UPDATE promotions SET starts_at = TIMESTAMPTZ '2026-10-07 07:00:00+00',"
        " ends_at = TIMESTAMPTZ '2026-10-14 06:59:00+00', updated_at = now()"
        " WHERE code = 'launch-2026-10'"
    )
