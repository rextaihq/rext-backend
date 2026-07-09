"""add_google_property_cache_and_tracking

Cached Google-side properties (GSC + GA4) per workspace, and the opt-in
analytics tracking flag on content_publishing_results. Backfills
tracking_enabled=true for publishing results whose site already has an
active Google site mapping, so previously working dashboards keep working.

Revision ID: e1f2a3b4c5d6
Revises: dad2e6bbb70c
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'dad2e6bbb70c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'google_gsc_properties',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('site_url', sa.String(length=500), nullable=False),
        sa.Column('permission_level', sa.String(length=100), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'site_url', name='uq_google_gsc_property_ws_url'),
    )
    op.create_index(
        op.f('ix_google_gsc_properties_workspace_id'),
        'google_gsc_properties', ['workspace_id'], unique=False,
    )
    print("  ✓ Created google_gsc_properties")

    op.create_table(
        'google_ga4_properties',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('property_id', sa.String(length=100), nullable=False),
        sa.Column('display_name', sa.String(length=300), nullable=True),
        sa.Column('account_display_name', sa.String(length=300), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'property_id', name='uq_google_ga4_property_ws_id'),
    )
    op.create_index(
        op.f('ix_google_ga4_properties_workspace_id'),
        'google_ga4_properties', ['workspace_id'], unique=False,
    )
    print("  ✓ Created google_ga4_properties")

    op.add_column(
        'content_publishing_results',
        sa.Column('tracking_enabled', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'content_publishing_results',
        sa.Column('tracking_enabled_at', sa.DateTime(timezone=True), nullable=True),
    )
    print("  ✓ Added tracking columns to content_publishing_results")

    # Backfill: keep already-mapped sites' published content tracked so
    # existing dashboards don't go dark after this migration.
    op.execute(
        """
        UPDATE content_publishing_results pr
        SET tracking_enabled = true,
            tracking_enabled_at = now()
        FROM google_site_mappings m
        WHERE m.site_id = pr.site_id
          AND m.is_active = true
          AND m.deleted_at IS NULL
          AND pr.status = 'published'
        """
    )
    print("  ✓ Backfilled tracking_enabled for already-mapped sites")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('content_publishing_results', 'tracking_enabled_at')
    op.drop_column('content_publishing_results', 'tracking_enabled')
    op.drop_table('google_ga4_properties')
    op.drop_table('google_gsc_properties')
    print("  ✓ Dropped google property cache tables + tracking columns")
