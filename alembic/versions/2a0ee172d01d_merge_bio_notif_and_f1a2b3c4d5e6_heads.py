"""merge bio_notif and f1a2b3c4d5e6 heads

Revision ID: 2a0ee172d01d
Revises: 20251111_bio_notif, f1a2b3c4d5e6
Create Date: 2025-11-11 13:13:04.794661

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a0ee172d01d'
down_revision: Union[str, Sequence[str], None] = ('20251111_bio_notif', 'f1a2b3c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
