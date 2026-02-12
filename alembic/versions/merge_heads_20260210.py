"""merge heads 20260210

Revision ID: merge_20260210
Revises: rev_add_fk_tb, 583351904869
Create Date: 2026-02-10 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'merge_20260210'
down_revision: Union[str, Sequence[str], None] = ('rev_add_fk_tb', '583351904869')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
