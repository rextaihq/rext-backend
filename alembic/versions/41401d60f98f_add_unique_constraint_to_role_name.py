"""add_unique_constraint_to_role_name

Revision ID: 41401d60f98f
Revises: c83afba99b68
Create Date: 2026-02-09 17:12:45.814119

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '41401d60f98f'
down_revision: Union[str, Sequence[str], None] = 'c83afba99b68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, check for and remove any duplicate role names
    # This query keeps the oldest role for each name and deletes duplicates
    try:
        op.execute("""
            DELETE FROM roles
            WHERE id NOT IN (
                SELECT MIN(id::text)::uuid
                FROM roles
                GROUP BY name
            )
        """)
    except Exception:
        pass

    # Add unique constraint if it doesn't already exist
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    constraints = inspector.get_unique_constraints('roles')
    constraint_names = [c['name'] for c in constraints]
    if 'uq_roles_name' not in constraint_names:
        op.create_unique_constraint('uq_roles_name', 'roles', ['name'])


def downgrade() -> None:
    op.drop_constraint('uq_roles_name', 'roles', type_='unique')
