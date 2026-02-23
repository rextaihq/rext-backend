"""add_html_content_to_email_logs

Revision ID: a9fe5f3d045c
Revises: 5a6b7c8d9e0f
Create Date: 2026-02-20 14:22:52.900962

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9fe5f3d045c'
down_revision: Union[str, Sequence[str], None] = '5a6b7c8d9e0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add html_content to email_logs."""
    op.add_column('email_logs', sa.Column('html_content', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema: remove html_content from email_logs."""
    op.drop_column('email_logs', 'html_content')
