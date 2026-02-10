"""fix_user_sessions_duplicate_indexes

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2025-10-05 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove duplicate indexes on user_sessions table (idempotent).

    The migration 23b403658069_add_user_sessions_table created duplicate indexes:
    - jti has both 'idx_user_sessions_jti' (non-unique) and 'ix_user_sessions_jti' (unique)
    - last_activity_at has both 'idx_user_sessions_last_activity' and 'ix_user_sessions_last_activity_at'

    We keep the Alembic-standard naming (with op.f() prefix) and remove the custom named duplicates.
    """
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)

    # Check if user_sessions table exists
    existing_tables = inspector.get_table_names()
    if 'user_sessions' not in existing_tables:
        print("⚠️  user_sessions table not found, skipping duplicate index removal")
        return

    # Get existing indexes on user_sessions table
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('user_sessions')}

    # Drop the duplicate indexes only if they exist (idempotent)
    if 'idx_user_sessions_jti' in existing_indexes:
        op.drop_index('idx_user_sessions_jti', table_name='user_sessions')
        print("✅ Dropped duplicate index: idx_user_sessions_jti")

    if 'idx_user_sessions_last_activity' in existing_indexes:
        op.drop_index('idx_user_sessions_last_activity', table_name='user_sessions')
        print("✅ Dropped duplicate index: idx_user_sessions_last_activity")


def downgrade() -> None:
    """Restore duplicate indexes on user_sessions table."""
    # Re-create the duplicate indexes
    op.create_index('idx_user_sessions_jti', 'user_sessions', ['jti'], unique=False)
    op.create_index('idx_user_sessions_last_activity', 'user_sessions', ['last_activity_at'], unique=False)
