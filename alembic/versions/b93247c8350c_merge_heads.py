"""merge_heads

Revision ID: b93247c8350c
Revises: rev_refund_status_enum, 6bcd0442f08e, c9893663dd80
Create Date: 2026-02-13 14:32:50.489183

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b93247c8350c'
down_revision: Union[str, Sequence[str], None] = ('rev_refund_status_enum', '6bcd0442f08e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
