"""add html_content to email_logs

Revision ID: 572a638e2089
Revises: 1f6d82da1298
Create Date: 2026-02-20 14:04:55.704317

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '572a638e2089'
down_revision: Union[str, Sequence[str], None] = '1f6d82da1298'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('email_logs', sa.Column('html_content', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('email_logs', 'html_content')
