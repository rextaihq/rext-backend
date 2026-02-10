"""add_generated_by_user_fields_to_topics

Revision ID: a8b9c0d1e2f3
Revises: ddef709e2283
Create Date: 2025-01-20 12:00:00.000000

Adds user tracking fields to topics table:
- generated_by_user_id (FK to users.id)
- generated_by_first_name
- generated_by_last_name

These fields track which user created each topic for display in the frontend.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'ddef709e2283'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add user tracking fields to topics table."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)

    # Get current columns
    columns = [c['name'] for c in inspector.get_columns('topics')]

    # Add generated_by_user_id if it doesn't exist
    if 'generated_by_user_id' not in columns:
        op.add_column(
            'topics',
            sa.Column('generated_by_user_id', postgresql.UUID(as_uuid=True), nullable=True)
        )
        # Add foreign key constraint
        op.create_foreign_key(
            'fk_topics_generated_by_user_id',
            'topics',
            'users',
            ['generated_by_user_id'],
            ['id'],
            ondelete='SET NULL'
        )

    # Add generated_by_first_name if it doesn't exist
    if 'generated_by_first_name' not in columns:
        op.add_column(
            'topics',
            sa.Column('generated_by_first_name', sa.String(), nullable=True)
        )

    # Add generated_by_last_name if it doesn't exist
    if 'generated_by_last_name' not in columns:
        op.add_column(
            'topics',
            sa.Column('generated_by_last_name', sa.String(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema - remove user tracking fields from topics table."""
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)

    # Get current foreign keys
    foreign_keys = [fk['name'] for fk in inspector.get_foreign_keys('topics')]

    # Drop foreign key if it exists
    if 'fk_topics_generated_by_user_id' in foreign_keys:
        op.drop_constraint('fk_topics_generated_by_user_id', 'topics', type_='foreignkey')

    # Get current columns
    columns = [c['name'] for c in inspector.get_columns('topics')]

    # Drop columns if they exist
    if 'generated_by_last_name' in columns:
        op.drop_column('topics', 'generated_by_last_name')

    if 'generated_by_first_name' in columns:
        op.drop_column('topics', 'generated_by_first_name')

    if 'generated_by_user_id' in columns:
        op.drop_column('topics', 'generated_by_user_id')

