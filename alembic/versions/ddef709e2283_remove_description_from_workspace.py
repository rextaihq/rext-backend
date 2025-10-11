"""remove description from workspace

Revision ID: ddef709e2283
Revises: 3955ee757268
Create Date: 2025-10-11 21:50:35.488745

Removes description column from workspace table as it's no longer needed.
Description field is being removed from the workspace creation flow.

WARNING: This migration will permanently delete all description data.
Ensure you have backed up any important description data before running this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ddef709e2283'
down_revision: Union[str, Sequence[str], None] = '3955ee757268'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove description column from workspace table."""
    # Drop the description column
    # WARNING: This will permanently delete all description data
    op.drop_column('workspace', 'description')


def downgrade() -> None:
    """Restore description column to workspace table."""
    # Add description column back as nullable TEXT
    # Note: Previously stored description data will NOT be restored
    op.add_column(
        'workspace',
        sa.Column(
            'description',
            sa.Text(),
            nullable=True,
            comment='Workspace description (deprecated, kept for rollback compatibility)'
        )
    )
