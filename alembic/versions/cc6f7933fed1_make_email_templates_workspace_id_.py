"""make_email_templates_workspace_id_nullable

Revision ID: cc6f7933fed1
Revises: b68e304117f0
Create Date: 2025-10-14 18:17:46.219180

Makes workspace_id nullable in email_templates table to support system-wide templates.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc6f7933fed1'
down_revision: Union[str, Sequence[str], None] = 'b68e304117f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make workspace_id nullable in email_templates table."""
    op.alter_column(
        'email_templates',
        'workspace_id',
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=True
    )


def downgrade() -> None:
    """Make workspace_id NOT NULL in email_templates table."""
    # Note: This will fail if there are NULL values
    op.alter_column(
        'email_templates',
        'workspace_id',
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=False
    )
