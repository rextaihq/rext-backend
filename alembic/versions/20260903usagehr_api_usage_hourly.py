"""add api_usage_hourly for durable API request totals

Revision ID: 20260903usagehr
Revises: 20260901ipallow
Create Date: 2026-09-03

API request volume was counted only in Redis, whose keys expire after an hour.
get_usage_stats then summed "up to 1440 minutes" of buckets when only ~50 still
existed, so 24h / 7d / 30d all returned roughly the last hour -- and a wider
period could report a smaller total as buckets aged out mid-read.

Redis keeps counting live (unchanged); a scheduled task copies completed
minutes in here so the longer periods have real history to read.
"""
import sqlalchemy as sa

from alembic import op

revision = "20260903usagehr"
down_revision = "20260901ipallow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_usage_hourly",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("hour_bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_ms", sa.BigInteger(), nullable=False,
                  server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    # The rollup upserts on this, so it must be unique.
    op.create_unique_constraint("uq_api_usage_hour", "api_usage_hourly", ["hour_bucket"])
    op.create_index("ix_api_usage_hourly_bucket", "api_usage_hourly", ["hour_bucket"])

    # Exact-once accounting between Redis and Postgres.
    #
    # Without a watermark, "which minutes are already in Postgres" is inferred
    # from whether the Redis key still exists -- so a failed delete, or a crash
    # between commit and delete, double-counts that minute forever. This table
    # records how far settlement has progressed, updated in the SAME
    # transaction as the rollup, so the boundary is atomic and deleting Redis
    # keys becomes best-effort cleanup rather than a correctness requirement.
    op.create_table(
        "api_usage_rollup_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("settled_through", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_api_usage_rollup_state_single_row"),
    )
    op.execute("INSERT INTO api_usage_rollup_state (id, settled_through) VALUES (1, NULL)")


def downgrade() -> None:
    op.drop_table("api_usage_rollup_state")
    op.drop_index("ix_api_usage_hourly_bucket", table_name="api_usage_hourly")
    op.drop_constraint("uq_api_usage_hour", "api_usage_hourly", type_="unique")
    op.drop_table("api_usage_hourly")
