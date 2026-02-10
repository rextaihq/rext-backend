"""add timezone to workspace

Revision ID: 3955ee757268
Revises: cb6e3a54663a
Create Date: 2025-10-11 21:46:53.503685

Adds timezone column to workspace table for storing IANA timezone identifiers.
This allows workspaces to have timezone-aware operations and scheduling.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3955ee757268'
down_revision: Union[str, Sequence[str], None] = 'cb6e3a54663a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add timezone column to workspace table."""
    # Add timezone column as nullable VARCHAR(50)
    op.add_column(
        'workspace',
        sa.Column(
            'timezone',
            sa.String(50),
            nullable=True,
            comment='IANA timezone identifier (e.g., America/New_York, UTC)'
        )
    )

    # Optional: Set default timezone for existing workspaces
    # This ensures all existing workspaces have a timezone value
    op.execute("UPDATE workspace SET timezone = 'UTC' WHERE timezone IS NULL")


def downgrade() -> None:
    """Remove timezone column from workspace table."""
    # Drop the timezone column
    op.drop_column('workspace', 'timezone')
