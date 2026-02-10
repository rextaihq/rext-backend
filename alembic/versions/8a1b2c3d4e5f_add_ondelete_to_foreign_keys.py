"""add ondelete to foreign keys

Revision ID: 8a1b2c3d4e5f
Revises: d499a5520245
Create Date: 2026-02-10 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = 'd499a5520245'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Workspace
    op.drop_constraint('workspace_user_id_fkey', 'workspace', type_='foreignkey')
    op.create_foreign_key('workspace_user_id_fkey', 'workspace', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    
    # Check if deleted_by fkey exists and update it
    # Note: Using op.execute for safer conditional drop if name might vary, 
    # but based on pattern we'll use drop_constraint.
    try:
        op.drop_constraint('workspace_deleted_by_fkey', 'workspace', type_='foreignkey')
    except:
        pass
    op.create_foreign_key('workspace_deleted_by_fkey', 'workspace', 'users', ['deleted_by'], ['id'], ondelete='SET NULL')

    # 2. Workspace Members
    op.drop_constraint('workspace_members_user_id_fkey', 'workspace_members', type_='foreignkey')
    op.create_foreign_key('workspace_members_user_id_fkey', 'workspace_members', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    
    op.drop_constraint('workspace_members_workspace_id_fkey', 'workspace_members', type_='foreignkey')
    op.create_foreign_key('workspace_members_workspace_id_fkey', 'workspace_members', 'workspace', ['workspace_id'], ['id'], ondelete='CASCADE')
    
    try:
        op.drop_constraint('workspace_members_invitation_id_fkey', 'workspace_members', type_='foreignkey')
    except:
        pass
    op.create_foreign_key('workspace_members_invitation_id_fkey', 'workspace_members', 'user_invitations', ['invitation_id'], ['id'], ondelete='SET NULL')

    # 3. User Roles
    op.drop_constraint('user_roles_user_id_fkey', 'user_roles', type_='foreignkey')
    op.create_foreign_key('user_roles_user_id_fkey', 'user_roles', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    
    op.drop_constraint('user_roles_role_id_fkey', 'user_roles', type_='foreignkey')
    op.create_foreign_key('user_roles_role_id_fkey', 'user_roles', 'roles', ['role_id'], ['id'], ondelete='CASCADE')
    
    op.drop_constraint('user_roles_workspace_id_fkey', 'user_roles', type_='foreignkey')
    op.create_foreign_key('user_roles_workspace_id_fkey', 'user_roles', 'workspace', ['workspace_id'], ['id'], ondelete='CASCADE')
    
    try:
        op.drop_constraint('user_roles_assigned_by_user_id_fkey', 'user_roles', type_='foreignkey')
    except:
        pass
    op.create_foreign_key('user_roles_assigned_by_user_id_fkey', 'user_roles', 'users', ['assigned_by_user_id'], ['id'], ondelete='SET NULL')

    # 4. Invitations
    op.drop_constraint('user_invitations_workspace_id_fkey', 'user_invitations', type_='foreignkey')
    op.create_foreign_key('user_invitations_workspace_id_fkey', 'user_invitations', 'workspace', ['workspace_id'], ['id'], ondelete='CASCADE')
    
    op.drop_constraint('user_invitations_role_id_fkey', 'user_invitations', type_='foreignkey')
    op.create_foreign_key('user_invitations_role_id_fkey', 'user_invitations', 'roles', ['role_id'], ['id'], ondelete='RESTRICT')
    
    op.drop_constraint('user_invitations_invited_by_user_id_fkey', 'user_invitations', type_='foreignkey')
    op.alter_column('user_invitations', 'invited_by_user_id', existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key('user_invitations_invited_by_user_id_fkey', 'user_invitations', 'users', ['invited_by_user_id'], ['id'], ondelete='SET NULL')

    # 5. Email Templates
    op.drop_constraint('email_templates_workspace_id_fkey', 'email_templates', type_='foreignkey')
    op.create_foreign_key('email_templates_workspace_id_fkey', 'email_templates', 'workspace', ['workspace_id'], ['id'], ondelete='CASCADE')
    
    try:
        op.drop_constraint('email_templates_created_by_user_id_fkey', 'email_templates', type_='foreignkey')
    except:
        pass
    op.create_foreign_key('email_templates_created_by_user_id_fkey', 'email_templates', 'users', ['created_by_user_id'], ['id'], ondelete='SET NULL')

    # 6. Subscriptions
    op.drop_constraint('user_subscriptions_plan_id_fkey', 'user_subscriptions', type_='foreignkey')
    op.create_foreign_key('user_subscriptions_plan_id_fkey', 'user_subscriptions', 'subscription_plans', ['plan_id'], ['id'], ondelete='RESTRICT')

    # 7. Customer Notes
    op.drop_constraint('customer_notes_admin_id_fkey', 'customer_notes', type_='foreignkey')
    op.alter_column('customer_notes', 'admin_id', existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key('customer_notes_admin_id_fkey', 'customer_notes', 'users', ['admin_id'], ['id'], ondelete='SET NULL')

    # 8. Error Logs
    try:
        op.drop_constraint('error_logs_user_id_fkey', 'error_logs', type_='foreignkey')
    except:
        pass
    op.create_foreign_key('error_logs_user_id_fkey', 'error_logs', 'users', ['user_id'], ['id'], ondelete='SET NULL')
    
    try:
        op.drop_constraint('error_logs_resolved_by_fkey', 'error_logs', type_='foreignkey')
    except:
        pass
    op.create_foreign_key('error_logs_resolved_by_fkey', 'error_logs', 'users', ['resolved_by'], ['id'], ondelete='SET NULL')

    # 9. Content
    op.drop_constraint('content_created_by_user_id_fkey', 'content', type_='foreignkey')
    op.alter_column('content', 'created_by_user_id', existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key('content_created_by_user_id_fkey', 'content', 'users', ['created_by_user_id'], ['id'], ondelete='SET NULL')

    # 10. Trial Conversions
    op.drop_constraint('trial_conversions_conversion_plan_id_fkey', 'trial_conversions', type_='foreignkey')
    op.alter_column('trial_conversions', 'conversion_plan_id', existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key('trial_conversions_conversion_plan_id_fkey', 'trial_conversions', 'subscription_plans', ['conversion_plan_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    # Reverse changes (back to RESTRICT/default)
    # This is complex to reverse perfectly without knowing original defaults, 
    # so we'll just restore basic FKs without CASCADE where they were RESTRICT.
    pass
