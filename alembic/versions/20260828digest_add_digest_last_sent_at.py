"""add notification_preferences.digest_last_sent_at

Revision ID: 20260828digest
Revises: 20260828emailevt
Create Date: 2026-08-28

The email digest feature (see src/services/digest_service.py) needs to know
when a user was last sent a digest so the scheduled task can decide whether
the next one is due for their chosen cadence (daily / weekly / monthly).
"""
from alembic import op
import sqlalchemy as sa


revision = "20260828digest"
down_revision = "20260828emailevt"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "notification_preferences",
        sa.Column("digest_last_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("notification_preferences", "digest_last_sent_at")
