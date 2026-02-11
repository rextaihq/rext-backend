"""add_fk_to_token_blacklist

Revision ID: rev_add_fk_tb
Revises: seed009
Create Date: 2026-02-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'rev_add_fk_tb'
down_revision = '86049af81ad3'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # First, delete orphaned records
    op.execute("""
        DELETE FROM token_blacklist tb
        WHERE NOT EXISTS (
            SELECT 1 FROM users u WHERE u.id = tb.user_id
        )
    """)
    
    # Add foreign key constraint with CASCADE delete
    op.create_foreign_key(
        'fk_token_blacklist_user_id',
        'token_blacklist', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

def downgrade() -> None:
    op.drop_constraint('fk_token_blacklist_user_id', 'token_blacklist', type_='foreignkey')
