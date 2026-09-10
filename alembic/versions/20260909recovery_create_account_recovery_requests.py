"""create account_recovery_requests table

Revision ID: 20260909recovery
Revises: 20260904rbacfloor, 20260907emailresend
Create Date: 2026-09-09

Backs the admin "Account Recovery" tab in User Management. A deleted or
deactivated user files a recovery request; it lands as ``pending`` and an admin
approves (restoring the account) or rejects it.

Also resolves the two open heads on stage (20260904rbacfloor scoped the global
'user' role; 20260907emailresend added the email.resend permission) — they
touch disjoint schema, so no reconciliation is needed beyond joining them here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260909recovery"
down_revision: Union[str, Sequence[str], None] = (
    "20260904rbacfloor",
    "20260907emailresend",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_recovery_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("request_note", sa.Text(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("requested_ip", sa.String(length=64), nullable=True),
        sa.Column("requested_user_agent", sa.String(length=512), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_account_recovery_requests_user_id"),
        "account_recovery_requests",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_account_recovery_requests_email"),
        "account_recovery_requests",
        ["email"],
    )
    op.create_index(
        op.f("ix_account_recovery_requests_status"),
        "account_recovery_requests",
        ["status"],
    )
    op.create_index(
        op.f("ix_account_recovery_requests_reviewed_by_user_id"),
        "account_recovery_requests",
        ["reviewed_by_user_id"],
    )
    # One open request per email.
    op.create_index(
        "uq_account_recovery_email_pending",
        "account_recovery_requests",
        ["email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_account_recovery_email_pending", table_name="account_recovery_requests"
    )
    op.drop_index(
        op.f("ix_account_recovery_requests_reviewed_by_user_id"),
        table_name="account_recovery_requests",
    )
    op.drop_index(
        op.f("ix_account_recovery_requests_status"),
        table_name="account_recovery_requests",
    )
    op.drop_index(
        op.f("ix_account_recovery_requests_email"),
        table_name="account_recovery_requests",
    )
    op.drop_index(
        op.f("ix_account_recovery_requests_user_id"),
        table_name="account_recovery_requests",
    )
    op.drop_table("account_recovery_requests")
