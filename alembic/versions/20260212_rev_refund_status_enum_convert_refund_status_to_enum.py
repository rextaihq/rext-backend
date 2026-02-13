"""Convert refund status from String to Enum type

Revision ID: rev_refund_status_enum
Revises: rev_add_fk_tb
Create Date: 2026-02-12 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'rev_refund_status_enum'
down_revision = 'rev_add_fk_tb'
branch_labels = None
depends_on = None

# Define the enum type
refundstatus_enum = postgresql.ENUM('pending', 'completed', 'failed', name='refundstatus', create_type=False)


def upgrade() -> None:
    # Step 1: Create the PostgreSQL ENUM type if it doesn't exist
    refundstatus_enum.create(op.get_bind(), checkfirst=True)

    # Step 2: Drop the existing default so PostgreSQL doesn't choke during type conversion
    op.alter_column('refunds', 'status', server_default=None)

    # Step 3: Alter the column from VARCHAR to ENUM
    # PostgreSQL requires an explicit USING clause to cast existing values
    op.execute(
        "ALTER TABLE refunds "
        "ALTER COLUMN status TYPE refundstatus "
        "USING status::refundstatus"
    )

    # Step 4: Set the new default
    op.alter_column(
        'refunds',
        'status',
        server_default='pending',
        existing_nullable=False,
    )


def downgrade() -> None:
    # Convert back to VARCHAR
    op.alter_column(
        'refunds',
        'status',
        type_=sa.String(20),
        existing_nullable=False,
        postgresql_using='status::text',
    )
    
    # Remove server default
    op.alter_column(
        'refunds',
        'status',
        server_default=None,
        existing_nullable=False,
    )

    # Drop the enum type
    # Note: checkfirst=True is safer
    refundstatus_enum.drop(op.get_bind(), checkfirst=True)
