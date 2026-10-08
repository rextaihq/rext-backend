"""users carry their answer on usage analytics

Revision ID: 368c3e36e8b5
Revises: f53595e1d014
Create Date: 2026-10-08 06:40:40.149198

FB2.31 (revnix/rext-control#712). Whether a person allows usage analytics was known only to
their browser, so the backend could send an event about them only without saying who. The
dashboard now stores the answer on the account: analytics_consent ("granted", "denied", or NULL
for no answer yet), analytics_region (where they were asked from, "eea" or "other": outside the
EEA analytics is on until refused), and analytics_consent_at (when they answered).

Only the table's shape changes: three nullable columns with no default and two checks that
every existing row passes (NULL passes a check). No row is added, removed or rewritten.

The downgrade refuses while any account holds an answer: dropping the columns would lose
refusals, and a later upgrade would then treat someone outside the EEA who had refused as
not having answered. The earlier code runs against this shape as it is (it never reads the
columns), so going back a release needs no downgrade. A region alone is not kept: the
dashboard writes it again at sign-in.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "368c3e36e8b5"
down_revision: Union[str, Sequence[str], None] = "f53595e1d014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("analytics_consent", sa.String(length=10), nullable=True))
    op.add_column("users", sa.Column("analytics_region", sa.String(length=10), nullable=True))
    op.add_column(
        "users", sa.Column("analytics_consent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_users_analytics_consent", "users", "analytics_consent IN ('granted', 'denied')"
    )
    op.create_check_constraint(
        "ck_users_analytics_region", "users", "analytics_region IN ('eea', 'other')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    answers = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM users WHERE analytics_consent IS NOT NULL"))
        .scalar()
    )
    if answers:
        raise RuntimeError(
            f"{answers} accounts hold an answer on usage analytics: the downgrade would"
            " delete them, refusals included. Keep them somewhere first."
        )
    op.drop_constraint("ck_users_analytics_region", "users", type_="check")
    op.drop_constraint("ck_users_analytics_consent", "users", type_="check")
    op.drop_column("users", "analytics_consent_at")
    op.drop_column("users", "analytics_region")
    op.drop_column("users", "analytics_consent")
