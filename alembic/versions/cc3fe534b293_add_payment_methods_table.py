"""add_payment_methods_table

Revision ID: cc3fe534b293
Revises: a87549e2c2de
Create Date: 2025-10-12 22:42:24.692523

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc3fe534b293'
down_revision: Union[str, Sequence[str], None] = 'a87549e2c2de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create payment_methods table."""
    op.create_table(
        'payment_methods',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider_payment_method_id', sa.String(length=255), nullable=False),
        sa.Column('provider_customer_id', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),  # card, bank_account, etc.
        sa.Column('is_default', sa.Boolean(), default=False, nullable=False),
        sa.Column('status', sa.String(length=50), default='active', nullable=False),
        sa.Column('card_brand', sa.String(length=50), nullable=True),  # visa, mastercard, etc.
        sa.Column('card_last4', sa.String(length=4), nullable=True),
        sa.Column('card_exp_month', sa.Integer(), nullable=True),
        sa.Column('card_exp_year', sa.Integer(), nullable=True),
        sa.Column('billing_email', sa.String(length=255), nullable=True),
        sa.Column('payment_metadata', sa.dialects.postgresql.JSONB(), default=dict, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('provider_payment_method_id', name='uq_provider_payment_method_id')
    )

    # Create indexes
    op.create_index('ix_payment_methods_user_id', 'payment_methods', ['user_id'])
    op.create_index('ix_payment_methods_provider_customer_id', 'payment_methods', ['provider_customer_id'])
    op.create_index('ix_payment_methods_is_default', 'payment_methods', ['user_id', 'is_default'])


def downgrade() -> None:
    """Drop payment_methods table."""
    op.drop_index('ix_payment_methods_is_default', table_name='payment_methods')
    op.drop_index('ix_payment_methods_provider_customer_id', table_name='payment_methods')
    op.drop_index('ix_payment_methods_user_id', table_name='payment_methods')
    op.drop_table('payment_methods')
