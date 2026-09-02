"""add api_usage_hourly and merge the two open heads

Revision ID: 20260902apiusage
Revises: 20260828digest, a1p2e3r4s5o6
Create Date: 2026-09-02

Durable per-endpoint API usage rollup.

API usage was counted only in Redis with a 3600s TTL, so "7 days" and
"30 days" both read the same ~1h window -- a wider period could even report a
*smaller* total as old minute buckets aged out. This table gives those periods
something real to read, and is what the "Top API Endpoints" chart needs (the
endpoint name was never recorded anywhere before).

This also merges the two heads that were left open at 20260827perms, which had
made `alembic upgrade head` fail outright ("Multiple head revisions are
present"). Nothing else in the tree could migrate until that was resolved.
"""
import sqlalchemy as sa

from alembic import op

revision = "20260902apiusage"
down_revision = ("20260828digest", "a1p2e3r4s5o6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_usage_hourly",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("hour_bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False, server_default="GET"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    # The rollup upserts on this key, so it must be unique.
    op.create_unique_constraint(
        "uq_api_usage_hour_endpoint_method",
        "api_usage_hourly", ["hour_bucket", "endpoint", "method"],
    )
    op.create_index("ix_api_usage_hourly_bucket", "api_usage_hourly", ["hour_bucket"])


def downgrade() -> None:
    op.drop_index("ix_api_usage_hourly_bucket", table_name="api_usage_hourly")
    op.drop_constraint("uq_api_usage_hour_endpoint_method", "api_usage_hourly", type_="unique")
    op.drop_table("api_usage_hourly")
