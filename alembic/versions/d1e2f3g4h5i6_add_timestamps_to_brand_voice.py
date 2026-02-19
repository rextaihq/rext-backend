"""add_timestamps_to_brand_voice

Revision ID: d1e2f3g4h5i6
Revises: ca05d74bd19c
Create Date: 2025-10-08 13:30:00.000000

Adds created_at and updated_at timestamp columns to brand_voice table
to track when brand voice data is created and modified.
"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3g4h5i6'
down_revision: Union[str, Sequence[str], None] = 'ca05d74bd19c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add created_at and updated_at columns to brand_voice table.

    The brand_voice table stores AI-generated brand intelligence data but
    currently lacks timestamp tracking. Adding these columns enables:
    - Tracking when brand voice was initially generated
    - Tracking when brand voice data was last updated
    - Consistency with other tables (knowledge_files, text_knowledge)
    """
    connection = op.get_bind()

    # Add created_at column with server default (nullable initially to allow existing rows)
    op.add_column('brand_voice',
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'),
                  nullable=True)
    )

    # Populate existing rows with current timestamp using PostgreSQL NOW()
    connection.execute(
        sa.text("UPDATE brand_voice SET created_at = NOW() WHERE created_at IS NULL")
    )

    # Make it non-nullable now that all rows have values
    op.alter_column('brand_voice', 'created_at', nullable=False)

    # Add updated_at column (nullable - only set when record is updated)
    # No server default - only updated when record is explicitly updated
    op.add_column('brand_voice',
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True)
    )

    print("✅ Added created_at and updated_at columns to brand_voice table")


def downgrade() -> None:
    """Remove created_at and updated_at columns from brand_voice table."""
    # Drop updated_at
    op.drop_column('brand_voice', 'updated_at')

    # Drop created_at
    op.drop_column('brand_voice', 'created_at')

    print("✅ Removed timestamp columns from brand_voice table")
