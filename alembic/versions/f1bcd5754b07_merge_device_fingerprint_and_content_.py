"""merge_device_fingerprint_and_content_category_heads

Revision ID: f1bcd5754b07
Revises: 6594f0648a61, c7a4e9b2d8f1
Create Date: 2026-07-29 14:38:14.391160

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1bcd5754b07'
down_revision: Union[str, Sequence[str], None] = ('6594f0648a61', 'c7a4e9b2d8f1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
