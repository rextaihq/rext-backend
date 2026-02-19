"""add_customer_notes_table

Revision ID: 02b176385c4f
Revises: 21341b11eeae
Create Date: 2025-10-13 09:19:14.905389

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '02b176385c4f'
down_revision: Union[str, Sequence[str], None] = '21341b11eeae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'customer_notes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('admin_id', sa.UUID(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_customer_notes_user_id', 'customer_notes', ['user_id'])
    op.create_index('ix_customer_notes_admin_id', 'customer_notes', ['admin_id'])
    op.create_index('ix_customer_notes_created_at', 'customer_notes', ['created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_customer_notes_created_at', 'customer_notes')
    op.drop_index('ix_customer_notes_admin_id', 'customer_notes')
    op.drop_index('ix_customer_notes_user_id', 'customer_notes')
    op.drop_table('customer_notes')
