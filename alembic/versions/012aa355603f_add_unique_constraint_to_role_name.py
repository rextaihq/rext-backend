"""add_unique_constraint_to_role_name

Revision ID: 012aa355603f
Revises: 2903f7581f46
Create Date: 2026-02-09 17:56:18.496469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '012aa355603f'
down_revision: Union[str, Sequence[str], None] = '2903f7581f46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, check for and remove any duplicate role names
    # This query keeps the oldest role for each name and deletes duplicates
    op.execute("""
        DELETE FROM roles
        WHERE id IN (
            SELECT id
            FROM (
                SELECT id,
                       ROW_NUMBER() OVER (PARTITION BY name ORDER BY created_at ASC, CAST(id AS TEXT) ASC) AS rnum
                FROM roles
            ) t
            WHERE t.rnum > 1
        )
    """)

    # Add unique constraint with explicit name for easier maintenance
    op.create_unique_constraint('uq_roles_name', 'roles', ['name'])


def downgrade() -> None:
    op.drop_constraint('uq_roles_name', 'roles', type_='unique')
