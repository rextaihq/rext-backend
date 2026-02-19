"""add_email_templates_table

Revision ID: g1h2i3j4k5l6
Revises: f9e8d7c6b5a4
Create Date: 2025-10-03 09:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, Sequence[str], None] = 'f9e8d7c6b5a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for template_type (idempotent)
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    
    # Check if enum type already exists
    result = bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'templatetype')"
    )).scalar()
    
    if not result:
        template_type_enum = postgresql.ENUM(
            'workspace_invitation',
            'invitation_accepted',
            'role_changed',
            'member_removed',
            'welcome',
            name='templatetype',
            create_type=False  # Don't auto-create, we'll do it manually
        )
        # Create the enum type explicitly
        bind.execute(sa.text(
            "CREATE TYPE templatetype AS ENUM ('workspace_invitation', 'invitation_accepted', 'role_changed', 'member_removed', 'welcome')"
        ))
    
    # Reference the existing enum type
    template_type_enum = postgresql.ENUM(
        'workspace_invitation',
        'invitation_accepted',
        'role_changed',
        'member_removed',
        'welcome',
        name='templatetype',
        create_type=False
    )

    # Create email_templates table
    op.create_table(
        'email_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('template_type', template_type_enum, nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('is_default', sa.Boolean(), default=False, nullable=False),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    )

    # Create indexes
    op.create_index(
        'idx_email_templates_workspace_id',
        'email_templates',
        ['workspace_id']
    )
    op.create_index(
        'idx_email_templates_type',
        'email_templates',
        ['template_type']
    )
    op.create_index(
        'idx_email_templates_workspace_type_active',
        'email_templates',
        ['workspace_id', 'template_type', 'is_active']
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_email_templates_workspace_type_active', table_name='email_templates')
    op.drop_index('idx_email_templates_type', table_name='email_templates')
    op.drop_index('idx_email_templates_workspace_id', table_name='email_templates')

    # Drop table
    op.drop_table('email_templates')

    # Drop enum type
    template_type_enum = postgresql.ENUM(
        'workspace_invitation',
        'invitation_accepted',
        'role_changed',
        'member_removed',
        'welcome',
        name='templatetype'
    )
    template_type_enum.drop(op.get_bind(), checkfirst=True)
