"""Seed default email templates."""

import asyncio
from sqlalchemy import select, text

from scripts.seeds.base import get_seed_session, utc_now


TEMPLATES = [
    {
        "template_type": "workspace_invitation",
        "subject": "You've been invited to join {workspace_name}",
        "body": """Hello {invitee_name},

{inviter_name} has invited you to join the workspace "{workspace_name}" as a {role_name}.

Click the link below to accept your invitation:
{invitation_url}

This invitation will expire in 7 days.

Best regards,
The Rext Team""",
    },
    {
        "template_type": "invitation_accepted",
        "subject": "{invitee_name} has accepted your invitation",
        "body": """Hello {inviter_name},

Good news! {invitee_name} ({invitee_email}) has accepted your invitation to join "{workspace_name}".

They now have {role_name} access to your workspace.

Best regards,
The Rext Team""",
    },
    {
        "template_type": "role_changed",
        "subject": "Your role has been updated in {workspace_name}",
        "body": """Hello {member_name},

Your role in the workspace "{workspace_name}" has been updated to {role_name}.

This change affects your permissions and access levels within the workspace.

If you have any questions about your new role, please contact your workspace administrator.

Best regards,
The Rext Team""",
    },
    {
        "template_type": "member_removed",
        "subject": "You have been removed from {workspace_name}",
        "body": """Hello {member_name},

You have been removed from the workspace "{workspace_name}".

You no longer have access to this workspace and its content.

If you believe this was done in error, please contact the workspace administrator.

Best regards,
The Rext Team""",
    },
    {
        "template_type": "welcome",
        "subject": "Welcome to {workspace_name}!",
        "body": """Hello {member_name},

Welcome to "{workspace_name}"! We're excited to have you on board.

You've been granted {role_name} access. Here's what you can do to get started:

1. Complete your profile
2. Explore the workspace features
3. Connect with other team members
4. Start creating content

If you have any questions, don't hesitate to reach out to your workspace administrator.

Best regards,
The Rext Team""",
    },
]


async def seed_email_templates():
    """Seed default email templates (idempotent — skips existing)."""
    async with get_seed_session() as session:
        created = 0
        skipped = 0

        for template in TEMPLATES:
            result = await session.execute(
                text("SELECT id FROM email_templates WHERE template_type = :type AND workspace_id IS NULL"),
                {"type": template["template_type"]},
            )
            existing = result.fetchone()

            if existing:
                skipped += 1
                continue

            now = utc_now()
            await session.execute(
                text("""
                    INSERT INTO email_templates (
                        id, workspace_id, template_type, subject, body,
                        is_active, is_default, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), NULL, :template_type, :subject, :body,
                        true, true, :created_at, :updated_at
                    )
                """),
                {
                    "template_type": template["template_type"],
                    "subject": template["subject"],
                    "body": template["body"],
                    "created_at": now,
                    "updated_at": now,
                },
            )
            created += 1

        print(f"Email templates: {created} created, {skipped} already existed")


if __name__ == "__main__":
    asyncio.run(seed_email_templates())
