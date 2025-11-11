"""Add bio field to users and expand notification preferences

Revision ID: 20251111_bio_notif
Revises: seed007
Create Date: 2025-11-11

This migration:
1. Adds bio field to users table
2. Adds digest_enabled to notification_preferences
3. Renames email_updates to email_content_updates
4. Renames in_app_updates to in_app_content_updates
5. Adds new notification categories:
   - email_team_activity / in_app_team_activity
   - email_security_alerts / in_app_security_alerts
   - email_billing_updates / in_app_billing_updates
   - email_product_updates / in_app_product_updates
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251111_bio_notif'
down_revision: Union[str, Sequence[str], None] = 'seed007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add bio field to users table
    op.add_column('users', sa.Column('bio', sa.String(length=500), nullable=True))

    # Add digest_enabled to notification_preferences
    op.add_column('notification_preferences',
                  sa.Column('digest_enabled', sa.Boolean(), nullable=False, server_default='true'))

    # Rename email_updates to email_content_updates
    op.alter_column('notification_preferences', 'email_updates',
                   new_column_name='email_content_updates',
                   existing_type=sa.Boolean(),
                   existing_nullable=False)

    # Rename in_app_updates to in_app_content_updates
    op.alter_column('notification_preferences', 'in_app_updates',
                   new_column_name='in_app_content_updates',
                   existing_type=sa.Boolean(),
                   existing_nullable=False)

    # Add new email notification categories
    op.add_column('notification_preferences',
                  sa.Column('email_team_activity', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('notification_preferences',
                  sa.Column('email_security_alerts', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('notification_preferences',
                  sa.Column('email_billing_updates', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('notification_preferences',
                  sa.Column('email_product_updates', sa.Boolean(), nullable=False, server_default='false'))

    # Add new in-app notification categories
    op.add_column('notification_preferences',
                  sa.Column('in_app_team_activity', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('notification_preferences',
                  sa.Column('in_app_security_alerts', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('notification_preferences',
                  sa.Column('in_app_billing_updates', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('notification_preferences',
                  sa.Column('in_app_product_updates', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove new in-app notification categories
    op.drop_column('notification_preferences', 'in_app_product_updates')
    op.drop_column('notification_preferences', 'in_app_billing_updates')
    op.drop_column('notification_preferences', 'in_app_security_alerts')
    op.drop_column('notification_preferences', 'in_app_team_activity')

    # Remove new email notification categories
    op.drop_column('notification_preferences', 'email_product_updates')
    op.drop_column('notification_preferences', 'email_billing_updates')
    op.drop_column('notification_preferences', 'email_security_alerts')
    op.drop_column('notification_preferences', 'email_team_activity')

    # Rename back email_content_updates to email_updates
    op.alter_column('notification_preferences', 'email_content_updates',
                   new_column_name='email_updates',
                   existing_type=sa.Boolean(),
                   existing_nullable=False)

    # Rename back in_app_content_updates to in_app_updates
    op.alter_column('notification_preferences', 'in_app_content_updates',
                   new_column_name='in_app_updates',
                   existing_type=sa.Boolean(),
                   existing_nullable=False)

    # Remove digest_enabled from notification_preferences
    op.drop_column('notification_preferences', 'digest_enabled')

    # Remove bio field from users table
    op.drop_column('users', 'bio')
