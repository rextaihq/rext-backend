"""add_google_analytics_integration

Revision ID: 20260706_ga_integration
Revises: d1e70992e366
Create Date: 2026-07-06

Adds tables for Google Analytics integration:
- workspace_google_connections: Stores GSC site and GA4 property selections per workspace
- google_analytics_metrics: Stores daily metrics from GSC and GA4 for published articles
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '20260706_ga_integration'
down_revision: Union[str, Sequence[str], None] = 'd1e70992e366'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create workspace_google_connections table
    op.create_table(
        'workspace_google_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('oauth_account_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('gsc_site_url', sa.String(length=500), nullable=True, comment='Selected GSC site URL (e.g., https://example.com/)'),
        sa.Column('ga4_property_id', sa.String(length=100), nullable=True, comment='Selected GA4 property ID (e.g., properties/123456789)'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True, comment='Last successful incremental sync timestamp'),
        sa.Column('last_backfill_completed_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when 16-month backfill completed'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['oauth_account_id'], ['oauth_accounts.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('workspace_id', name='uq_workspace_google_connection'),
    )
    
    # Create indexes for workspace_google_connections
    op.create_index('ix_workspace_google_connections_workspace_id', 'workspace_google_connections', ['workspace_id'], unique=True)
    op.create_index('ix_workspace_google_connections_oauth_account_id', 'workspace_google_connections', ['oauth_account_id'], unique=False)

    # Create google_analytics_metrics table
    op.create_table(
        'google_analytics_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('article_external_url', sa.String(length=1000), nullable=False, comment='Normalized external URL from ContentPublishingResult'),
        sa.Column('date', sa.Date(), nullable=False, comment='Date for which metrics are recorded'),
        sa.Column('source', sa.String(length=10), nullable=False, comment="Data source: 'gsc' or 'ga4'"),
        sa.Column('metrics', postgresql.JSONB(), nullable=False, comment='Metrics object: {clicks, impressions, ctr, position} for GSC or {sessions, active_users, engagement_rate, conversions} for GA4'),
        sa.Column('query_keyword', sa.String(length=500), nullable=True, comment='Search query keyword (GSC only, NULL for GA4)'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('workspace_id', 'article_external_url', 'date', 'source', 'query_keyword', name='uq_ga_metric_unique'),
    )
    
    # Create indexes for google_analytics_metrics
    op.create_index('ix_google_analytics_metrics_workspace_id', 'google_analytics_metrics', ['workspace_id'], unique=False)
    op.create_index('ix_google_analytics_metrics_date', 'google_analytics_metrics', ['date'], unique=False)
    op.create_index('ix_ga_metrics_workspace_url_date_source', 'google_analytics_metrics', ['workspace_id', 'article_external_url', 'date', 'source'], unique=False)


def downgrade() -> None:
    # Drop google_analytics_metrics table and its indexes
    op.drop_index('ix_ga_metrics_workspace_url_date_source', table_name='google_analytics_metrics')
    op.drop_index('ix_google_analytics_metrics_date', table_name='google_analytics_metrics')
    op.drop_index('ix_google_analytics_metrics_workspace_id', table_name='google_analytics_metrics')
    op.drop_table('google_analytics_metrics')
    
    # Drop workspace_google_connections table and its indexes
    op.drop_index('ix_workspace_google_connections_oauth_account_id', table_name='workspace_google_connections')
    op.drop_index('ix_workspace_google_connections_workspace_id', table_name='workspace_google_connections')
    op.drop_table('workspace_google_connections')
