"""add unique constraint to permission name

Revision ID: 996f2197158c
Revises: 1f6d82da1298
Create Date: 2026-02-17 11:03:55.443519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '996f2197158c'
down_revision: Union[str, Sequence[str], None] = '1f6d82da1298'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
    "uq_permissions_name",
    "permissions",
    ["name"],
)



def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
    "uq_permissions_name",
    "permissions",
    type_="unique"
)

