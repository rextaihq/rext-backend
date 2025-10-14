"""seed005_default_email_templates

Revision ID: seed005
Revises: b2c3d4e5f6g7
Create Date: 2025-10-05 00:02:00.000000

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'seed005'
down_revision: Union[str, Sequence[str], None] = 'cc6f7933fed1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed default email templates for all template types.

    Creates system default templates that can be used by any workspace.
    Templates include common variable placeholders:
    - {workspace_name}
    - {inviter_name}
    - {invitee_name}
    - {invitee_email}
    - {role_name}
    - {invitation_url}
    - {member_name}
    """
    connection = op.get_bind()

    # Check if email_templates table exists
    from sqlalchemy import inspect
    inspector = inspect(connection)
    if 'email_templates' not in inspector.get_table_names():
        print("⚠️ email_templates table does not exist. Skipping seed migration.")
        print("   Please ensure migration g1h2i3j4k5l6_add_email_templates_table is applied first.")
        return

    # Get a system workspace ID (we'll use the first workspace, or create templates with NULL workspace_id)
    # For system defaults, we'll use NULL workspace_id and set is_default=True

    templates = [
        {
            'template_type': 'workspace_invitation',
            'subject': 'You\'ve been invited to join {workspace_name}',
            'body': '''Hello {invitee_name},

{inviter_name} has invited you to join the workspace "{workspace_name}" as a {role_name}.

Click the link below to accept your invitation:
{invitation_url}

This invitation will expire in 7 days.

Best regards,
The Wrext Team''',
        },
        {
            'template_type': 'invitation_accepted',
            'subject': '{invitee_name} has accepted your invitation',
            'body': '''Hello {inviter_name},

Good news! {invitee_name} ({invitee_email}) has accepted your invitation to join "{workspace_name}".

They now have {role_name} access to your workspace.

Best regards,
The Wrext Team''',
        },
        {
            'template_type': 'role_changed',
            'subject': 'Your role has been updated in {workspace_name}',
            'body': '''Hello {member_name},

Your role in the workspace "{workspace_name}" has been updated to {role_name}.

This change affects your permissions and access levels within the workspace.

If you have any questions about your new role, please contact your workspace administrator.

Best regards,
The Wrext Team''',
        },
        {
            'template_type': 'member_removed',
            'subject': 'You have been removed from {workspace_name}',
            'body': '''Hello {member_name},

You have been removed from the workspace "{workspace_name}".

You no longer have access to this workspace and its content.

If you believe this was done in error, please contact the workspace administrator.

Best regards,
The Wrext Team''',
        },
        {
            'template_type': 'welcome',
            'subject': 'Welcome to {workspace_name}!',
            'body': '''Hello {member_name},

Welcome to "{workspace_name}"! We're excited to have you on board.

You've been granted {role_name} access. Here's what you can do to get started:

1. Complete your profile
2. Explore the workspace features
3. Connect with other team members
4. Start creating content

If you have any questions, don't hesitate to reach out to your workspace administrator.

Best regards,
The Wrext Team''',
        },
    ]

    # Create system-wide email templates (workspace_id = NULL for global templates)
    for template in templates:
        # Check if template already exists
        result = connection.execute(
            sa.text("SELECT id FROM email_templates WHERE template_type = :type AND workspace_id IS NULL"),
            {'type': template['template_type']}
        )
        existing = result.fetchone()

        if existing:
            print(f"⚠️  Email template '{template['template_type']}' already exists, skipping...")
            continue

        connection.execute(
            sa.text("""
                INSERT INTO email_templates (
                    id,
                    workspace_id,
                    template_type,
                    subject,
                    body,
                    is_active,
                    is_default,
                    created_at,
                    updated_at
                ) VALUES (
                    gen_random_uuid(),
                    NULL,
                    :template_type,
                    :subject,
                    :body,
                    true,
                    true,
                    :created_at,
                    :updated_at
                )
            """),
            {
                'template_type': template['template_type'],
                'subject': template['subject'],
                'body': template['body'],
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
            }
        )

    print(f"✅ Created {len(templates)} system-wide email templates (global, not workspace-specific)")


def downgrade() -> None:
    """Remove default email templates."""
    connection = op.get_bind()

    # Delete all system-wide default templates (workspace_id IS NULL)
    connection.execute(
        sa.text("DELETE FROM email_templates WHERE is_default = true AND workspace_id IS NULL")
    )

    print("✅ Removed system-wide default email templates")
