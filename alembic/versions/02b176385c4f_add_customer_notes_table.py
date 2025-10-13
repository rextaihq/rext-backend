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
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
