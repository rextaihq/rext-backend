"""add account_creation_ip_allowlist table

Revision ID: 20260901ipallow
Revises: 20260828digest, a1p2e3r4s5o6
Create Date: 2026-09-01

Backs the admin-managed account-creation IP allowlist. Platform admins add /
remove public IPs or CIDR ranges here (via /api/v1/admin/account-creation-allowlist)
and any active entry lets that client bypass the per-device cap on creating
multiple non-paid accounts (see check_device_account_limit in
src/api/routes/users/auth.py).

This revision also merges the two pre-existing migration heads
(20260828digest and a1p2e3r4s5o6) back into a single head.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260901ipallow"
down_revision: Union[str, Sequence[str], None] = ("20260828digest", "a1p2e3r4s5o6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_creation_ip_allowlist",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address", name="uq_account_creation_ip_allowlist_ip"),
    )
    op.create_index(
        "ix_account_creation_ip_allowlist_is_active",
        "account_creation_ip_allowlist",
        ["is_active"],
    )
    op.create_index(
        "ix_account_creation_ip_allowlist_created_by",
        "account_creation_ip_allowlist",
        ["created_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_creation_ip_allowlist_created_by",
        "account_creation_ip_allowlist",
    )
    op.drop_index(
        "ix_account_creation_ip_allowlist_is_active",
        "account_creation_ip_allowlist",
    )
    op.drop_table("account_creation_ip_allowlist")
