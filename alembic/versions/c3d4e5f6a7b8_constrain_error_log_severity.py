"""constrain_error_log_severity

Revision ID: c3d4e5f6a7b8
Revises: a9fe5f3d045c
Create Date: 2026-02-24 12:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'a9fe5f3d045c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Normalize severity data and enforce check constraint."""
    # Step 1: Normalize any non-compliant values to 'error' before applying constraint
    op.execute(
        """
        UPDATE error_logs
        SET severity = 'error'
        WHERE severity IS NULL
           OR severity NOT IN ('error', 'warning', 'critical')
        """
    )

    # Step 2: Alter the column from String(20) to VARCHAR with a CHECK constraint
    op.alter_column(
        "error_logs",
        "severity",
        existing_type=sa.String(length=20),
        type_=sa.Enum(
            "error",
            "warning",
            "critical",
            name="error_log_severity",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Remove check constraint and revert severity column to String(20)."""
    op.alter_column(
        "error_logs",
        "severity",
        existing_type=sa.Enum(
            "error",
            "warning",
            "critical",
            name="error_log_severity",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
