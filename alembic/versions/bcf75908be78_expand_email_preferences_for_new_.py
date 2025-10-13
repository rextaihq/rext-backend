"""expand_email_preferences_for_new_notification_types

Revision ID: bcf75908be78
Revises: b22009b4e3af
Create Date: 2025-10-13 13:00:01.856482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcf75908be78'
down_revision: Union[str, Sequence[str], None] = 'b22009b4e3af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add new email preference columns."""
    # Content generation preferences
    op.add_column('email_preferences', sa.Column('content_generation_started', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('content_generation_completed', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('content_generation_failed', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('content_published', sa.Boolean(), nullable=False, server_default='true'))

    # Billing preferences
    op.add_column('email_preferences', sa.Column('payment_succeeded', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('payment_failed', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('subscription_cancelled', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('subscription_expiring_soon', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('trial_ending_soon', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('usage_limit_warning', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('usage_limit_exceeded', sa.Boolean(), nullable=False, server_default='true'))

    # Knowledge base preferences
    op.add_column('email_preferences', sa.Column('kb_processing_completed', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('email_preferences', sa.Column('kb_processing_failed', sa.Boolean(), nullable=False, server_default='true'))

    # Digest preferences
    op.add_column('email_preferences', sa.Column('digest_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('email_preferences', sa.Column('digest_frequency', sa.String(20), nullable=False, server_default="'weekly'"))


def downgrade() -> None:
    """Downgrade schema - Remove new email preference columns."""
    # Drop digest preferences
    op.drop_column('email_preferences', 'digest_frequency')
    op.drop_column('email_preferences', 'digest_enabled')

    # Drop knowledge base preferences
    op.drop_column('email_preferences', 'kb_processing_failed')
    op.drop_column('email_preferences', 'kb_processing_completed')

    # Drop billing preferences
    op.drop_column('email_preferences', 'usage_limit_exceeded')
    op.drop_column('email_preferences', 'usage_limit_warning')
    op.drop_column('email_preferences', 'trial_ending_soon')
    op.drop_column('email_preferences', 'subscription_expiring_soon')
    op.drop_column('email_preferences', 'subscription_cancelled')
    op.drop_column('email_preferences', 'payment_failed')
    op.drop_column('email_preferences', 'payment_succeeded')

    # Drop content generation preferences
    op.drop_column('email_preferences', 'content_published')
    op.drop_column('email_preferences', 'content_generation_failed')
    op.drop_column('email_preferences', 'content_generation_completed')
    op.drop_column('email_preferences', 'content_generation_started')
