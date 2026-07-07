"""add_google_search_console_ga4_integration

Revision ID: 9e10ee847769
Revises: 20260622trial
Create Date: 2026-07-06 12:57:23.892515

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9e10ee847769'
down_revision: Union[str, Sequence[str], None] = '20260622trial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. google_integrations — one Google OAuth connection per workspace
    op.create_table(
        'google_integrations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('google_account_email', sa.String(length=255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=True, comment='OAuth access token (encrypted)'),
        sa.Column('refresh_token', sa.Text(), nullable=True, comment='OAuth refresh token (encrypted)'),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('connected_by_user_id', sa.UUID(), nullable=True),
        sa.Column('last_refreshed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connected_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_google_integrations_workspace_id'), 'google_integrations', ['workspace_id'], unique=False
    )

    # 2. google_site_mappings — GSC/GA4 property per connected WordPress site
    op.create_table(
        'google_site_mappings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('site_id', sa.UUID(), nullable=False),
        sa.Column('gsc_site_url', sa.String(length=500), nullable=True),
        sa.Column('ga4_property_id', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', name='uq_google_site_mappings_site_id'),
    )
    op.create_index(
        op.f('ix_google_site_mappings_workspace_id'), 'google_site_mappings', ['workspace_id'], unique=False
    )
    op.create_index(
        op.f('ix_google_site_mappings_site_id'), 'google_site_mappings', ['site_id'], unique=True
    )

    # 3. content_performance_metrics — daily GSC/GA4 metric snapshots per published URL
    op.create_table(
        'content_performance_metrics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('content_id', sa.UUID(), nullable=False),
        sa.Column('publishing_result_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['publishing_result_id'], ['content_publishing_results.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'publishing_result_id', 'source', 'metric_date',
            name='uq_content_performance_metric_result_source_date',
        ),
    )
    op.create_index(
        op.f('ix_content_performance_metrics_content_id'), 'content_performance_metrics', ['content_id'], unique=False
    )
    op.create_index(
        op.f('ix_content_performance_metrics_publishing_result_id'),
        'content_performance_metrics', ['publishing_result_id'], unique=False,
    )
    op.create_index(
        op.f('ix_content_performance_metrics_workspace_id'), 'content_performance_metrics', ['workspace_id'], unique=False
    )
    op.create_index(
        op.f('ix_content_performance_metrics_source'), 'content_performance_metrics', ['source'], unique=False
    )
    op.create_index(
        op.f('ix_content_performance_metrics_metric_date'), 'content_performance_metrics', ['metric_date'], unique=False
    )

    print("  ✓ Created google_integrations, google_site_mappings, content_performance_metrics")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('content_performance_metrics')
    op.drop_table('google_site_mappings')
    op.drop_table('google_integrations')
    print("  ✓ Dropped google_integrations, google_site_mappings, content_performance_metrics")
