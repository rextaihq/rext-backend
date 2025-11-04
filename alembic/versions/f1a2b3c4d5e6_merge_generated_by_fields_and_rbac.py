"""merge_generated_by_fields_and_rbac

Revision ID: f1a2b3c4d5e6
Revises: a8b9c0d1e2f3, b61d3f424d6f
Create Date: 2025-01-20 13:00:00.000000

Merges two migration branches:
- a8b9c0d1e2f3: Adds generated_by_user_id fields to topics table
- b61d3f424d6f: Fixes RBAC permission matrix
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = ('a8b9c0d1e2f3', 'b61d3f424d6f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge migration - no schema changes needed."""
    pass


def downgrade() -> None:
    """Downgrade merge - no schema changes needed."""
    pass

