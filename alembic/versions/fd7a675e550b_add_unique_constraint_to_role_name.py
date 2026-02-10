"""add_unique_constraint_to_role_name

Revision ID: fd7a675e550b
Revises: 2d09d2bad33e
Create Date: 2026-02-10 10:39:36.021600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd7a675e550b'
down_revision: Union[str, Sequence[str], None] = '2d09d2bad33e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, check for and remove any duplicate role names
    # This query keeps the oldest role for each name and deletes duplicates
    op.execute("""
        DELETE FROM roles
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT DISTINCT ON (name) id
                FROM roles
                ORDER BY name, created_at ASC
            ) t
        )
    """)

    # Add unique constraint with explicit name for easier maintenance
    op.create_unique_constraint('uq_roles_name', 'roles', ['name'])


def downgrade() -> None:
    op.drop_constraint('uq_roles_name', 'roles', type_='unique')
