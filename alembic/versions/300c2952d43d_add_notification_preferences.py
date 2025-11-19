"""add notification preferences

Revision ID: 300c2952d43d
Revises: 2a0ee172d01d
Create Date: 2025-11-17 18:37:56.033243

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '300c2952d43d'
down_revision: Union[str, Sequence[str], None] = '2a0ee172d01d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    def column_exists(table_name: str, column_name: str) -> bool:
        result = conn.execute(
        text(
            """
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name=:table_name AND column_name=:column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
        return bool(result.fetchone())

    # Helper to safely add a column
    def add_column_if_not_exists(table_name, column):
        if not column_exists(table_name, column.name):
            op.add_column(table_name, column)

    table = 'notification_preferences'

    # ==============================
    # WORKSPACE NOTIFICATIONS
    # ==============================
    add_column_if_not_exists(table, sa.Column('ws_invite_received', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('ws_invite_accepted', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('ws_role_changed', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('ws_member_removed', sa.Boolean(), nullable=False, server_default='true'))

    # ==============================
    # CONTENT GENERATION
    # ==============================
    add_column_if_not_exists(table, sa.Column('gen_started', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('gen_completed', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('gen_failed', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('gen_published', sa.Boolean(), nullable=False, server_default='true'))

    # ==============================
    # BILLING & PAYMENTS
    # ==============================
    add_column_if_not_exists(table, sa.Column('billing_payment_success', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('billing_payment_failed', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('billing_subscription_cancelled', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('billing_subscription_expiring', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('billing_trial_ending', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('billing_usage_limit_warning', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('billing_usage_limit_exceeded', sa.Boolean(), nullable=False, server_default='true'))

    # ==============================
    # KNOWLEDGE BASE
    # ==============================
    add_column_if_not_exists(table, sa.Column('kb_processing_completed', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('kb_processing_failed', sa.Boolean(), nullable=False, server_default='true'))

    # ==============================
    # EMAIL DIGEST
    # ==============================
    add_column_if_not_exists(table, sa.Column('digest_enabled', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('digest_frequency', sa.String(length=20), nullable=False, server_default='daily'))

    # ==============================
    # MARKETING COMMUNICATIONS
    # ==============================
    add_column_if_not_exists(table, sa.Column('marketing_updates', sa.Boolean(), nullable=False, server_default='false'))

    # ==============================
    # GLOBAL TOGGLES
    # ==============================
    add_column_if_not_exists(table, sa.Column('email_notifications', sa.Boolean(), nullable=False, server_default='true'))
    add_column_if_not_exists(table, sa.Column('in_app_notifications', sa.Boolean(), nullable=False, server_default='true'))