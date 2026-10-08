"""credit grants carry their source: a super admin's added credits are grants too

Revision ID: f53595e1d014
Revises: 87d0834f8a64
Create Date: 2026-10-07 21:38:26.512309

FB2.28 (revnix/rext-control#709). A super admin adds credits to a user, and they are kept as
credit_grants rows beside the promotions' bonuses. A grant now says where it came from (source:
"promotion" or "admin"); an admin's grant points at no promotion, so promotion_id may be NULL, and
it carries the reason shown to the customer and the admin who added it. The check keeps the two
kinds whole: a promotion's grant has its promotion, an admin's has its reason.

Only the table's shape changes. Every existing row is a promotion's bonus: it takes the default
source, keeps its promotion and passes the check, and no row is added, removed or rewritten.
uq_credit_grants_subscription_promotion stays: PostgreSQL treats NULLs as distinct in it, so a
subscription holds any number of admin grants and still one grant per promotion.

The downgrade refuses while admin grants exist: they have no promotion to point at, and putting
NOT NULL back would mean deleting credits customers were given. The earlier code runs against this
shape as it is (it writes promotion grants only), so going back a release needs no downgrade.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f53595e1d014"
down_revision: Union[str, Sequence[str], None] = "87d0834f8a64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_CHECK = (
    "(source = 'promotion' AND promotion_id IS NOT NULL)"
    " OR (source = 'admin' AND reason IS NOT NULL)"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "credit_grants",
        sa.Column("source", sa.String(length=20), server_default="promotion", nullable=False),
    )
    op.add_column("credit_grants", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("credit_grants", sa.Column("granted_by", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_credit_grants_granted_by"), "credit_grants", ["granted_by"], unique=False
    )
    op.create_foreign_key(
        "credit_grants_granted_by_fkey",
        "credit_grants",
        "users",
        ["granted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("credit_grants", "promotion_id", existing_type=sa.UUID(), nullable=True)
    op.create_check_constraint("ck_credit_grants_source", "credit_grants", SOURCE_CHECK)


def downgrade() -> None:
    """Downgrade schema."""
    admin_grants = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM credit_grants WHERE source = 'admin'"))
        .scalar()
    )
    if admin_grants:
        raise RuntimeError(
            f"{admin_grants} admin-added credit grants exist and have no promotion: the downgrade"
            " would have to delete them. Decide what happens to those credits first."
        )
    op.drop_constraint("ck_credit_grants_source", "credit_grants", type_="check")
    op.alter_column("credit_grants", "promotion_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("credit_grants_granted_by_fkey", "credit_grants", type_="foreignkey")
    op.drop_index(op.f("ix_credit_grants_granted_by"), table_name="credit_grants")
    op.drop_column("credit_grants", "granted_by")
    op.drop_column("credit_grants", "reason")
    op.drop_column("credit_grants", "source")
