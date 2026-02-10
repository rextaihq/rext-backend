"""add_updated_at_tracking_columns

Revision ID: c3d4e5f6g7h8
Revises: seed005
Create Date: 2025-10-05 00:03:00.000000

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, Sequence[str], None] = 'seed005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add updated_at columns to content_ai_config and content_versions tables.

    These tables currently only have created_at but should have updated_at for consistency
    with other content tables (content, content_metadata, content_seo_data, etc.).
    """
    connection = op.get_bind()

    # Add updated_at to content_ai_config
    op.add_column('content_ai_config',
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True)
    )

    # Populate existing rows with created_at value
    connection.execute(
        sa.text("UPDATE content_ai_config SET updated_at = created_at WHERE updated_at IS NULL")
    )

    # Make it non-nullable now that all rows have values
    op.alter_column('content_ai_config', 'updated_at', nullable=False)

    # Add updated_at to content_versions
    op.add_column('content_versions',
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True)
    )

    # Populate existing rows with created_at value
    connection.execute(
        sa.text("UPDATE content_versions SET updated_at = created_at WHERE updated_at IS NULL")
    )

    # Make it non-nullable now that all rows have values
    op.alter_column('content_versions', 'updated_at', nullable=False)

    print("✅ Added updated_at columns to content_ai_config and content_versions tables")


def downgrade() -> None:
    """Remove updated_at columns from content_ai_config and content_versions tables."""
    # Drop updated_at from content_versions
    op.drop_column('content_versions', 'updated_at')

    # Drop updated_at from content_ai_config
    op.drop_column('content_ai_config', 'updated_at')

    print("✅ Removed updated_at columns from content_ai_config and content_versions tables")
