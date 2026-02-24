"""constrain_error_log_severity

Revision ID: dd7ac82b3cb0
Revises: a9fe5f3d045c
Create Date: 2026-02-23 16:04:32.274319

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembics.
revision: str = 'dd7ac82b3cb0'
down_revision: Union[str, Sequence[str], None] = 'a9fe5f3d045c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
