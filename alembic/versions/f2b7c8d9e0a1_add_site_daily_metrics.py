"""add_site_daily_metrics

Site-level (whole property, no page filter) daily GSC/GA4 metric snapshots,
one row per (site, source, date). Powers the dashboard's site-wide totals;
content_performance_metrics stays as-is and keeps powering the per-content
modules (inventory, health, opportunity, ranking diagnosis).

Purely additive — creates one new table, no changes to existing data.

Revision ID: f2b7c8d9e0a1
Revises: e1f2a3b4c5d6
Create Date: 2026-07-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'f2b7c8d9e0a1'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'site_daily_metrics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('site_id', sa.UUID(), nullable=False,
                  comment='WorkspaceIntegration.id of the connected WordPress site'),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('metrics', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', 'source', 'metric_date',
                            name='uq_site_daily_metric_site_source_date'),
    )
    op.create_index(op.f('ix_site_daily_metrics_workspace_id'), 'site_daily_metrics', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_site_daily_metrics_site_id'), 'site_daily_metrics', ['site_id'], unique=False)
    op.create_index(op.f('ix_site_daily_metrics_source'), 'site_daily_metrics', ['source'], unique=False)
    op.create_index(op.f('ix_site_daily_metrics_metric_date'), 'site_daily_metrics', ['metric_date'], unique=False)
    print("  ✓ Created site_daily_metrics")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('site_daily_metrics')
    print("  ✓ Dropped site_daily_metrics")
