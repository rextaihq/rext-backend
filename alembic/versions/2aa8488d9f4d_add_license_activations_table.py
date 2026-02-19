"""add_license_activations_table

Revision ID: 2aa8488d9f4d
Revises: efa024600a98
Create Date: 2025-10-18 18:49:28.590138

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2aa8488d9f4d'
down_revision: Union[str, Sequence[str], None] = 'efa024600a98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create license_activations table
    op.create_table(
        'license_activations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('license_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('instance_id', sa.String(255), nullable=False, comment='Device ID, domain, or unique instance identifier'),
        sa.Column('instance_name', sa.String(255), nullable=True, comment='Human-readable name for the instance'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('activated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True, comment='Last time this activation was validated/checked'),
        sa.Column('activation_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb"), comment='Additional info: IP, user agent, OS, etc.'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['license_id'], ['licenses.id'], ondelete='CASCADE')
    )

    # Create indexes
    op.create_index('idx_license_activations_license_id', 'license_activations', ['license_id'])
    op.create_index('idx_license_activations_instance_id', 'license_activations', ['instance_id'])
    op.create_index('idx_license_activations_license_instance', 'license_activations', ['license_id', 'instance_id'])
    op.create_index('idx_license_activations_active', 'license_activations', ['license_id', 'is_active'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_license_activations_active', table_name='license_activations')
    op.drop_index('idx_license_activations_license_instance', table_name='license_activations')
    op.drop_index('idx_license_activations_instance_id', table_name='license_activations')
    op.drop_index('idx_license_activations_license_id', table_name='license_activations')

    # Drop table
    op.drop_table('license_activations')
