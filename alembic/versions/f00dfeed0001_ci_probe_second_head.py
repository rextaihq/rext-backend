"""Throwaway: a second migration head for the CI probe (never merged)

Revision ID: f00dfeed0001
Revises: 3c9e1e5d5028
"""

from typing import Sequence, Union

revision: str = "f00dfeed0001"
down_revision: Union[str, Sequence[str], None] = "3c9e1e5d5028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
