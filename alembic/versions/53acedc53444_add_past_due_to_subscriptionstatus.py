"""add PAST_DUE to subscriptionstatus

Revision ID: 53acedc53444
Revises: 1ff9280add01
Create Date: 2026-03-25 21:26:52.516474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '53acedc53444'
down_revision: Union[str, Sequence[str], None] = '1ff9280add01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add new enum value
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE 'PAST_DUE'")


def downgrade():
    # PostgreSQL cannot remove enum values easily; leave empty or skip
    pass