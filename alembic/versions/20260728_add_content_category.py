"""add content category

Revision ID: c7a4e9b2d8f1
Revises: 842403e5c605
Create Date: 2026-07-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7a4e9b2d8f1"
down_revision: Union[str, Sequence[str], None] = "842403e5c605"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content",
        sa.Column(
            "category",
            sa.Text(),
            nullable=True,
            comment="WordPress category name",
        ),
    )


def downgrade() -> None:
    op.drop_column("content", "category")
