"""add_approval_workflow_permissions

Add 10 new permissions for content approval workflow and member management:
- Content workflow: submit_for_review, approve, reject, publish
- Workspace management: transfer_ownership, manage_billing
- Member management: read, invite, remove, update_role

Revision ID: d0f311c36ace
Revises: 4b6dc95bfde9
Create Date: 2025-10-20 11:09:02.099458

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
import uuid

# revision identifiers, used by Alembic.
revision: str = 'd0f311c36ace'
down_revision: Union[str, Sequence[str], None] = '4b6dc95bfde9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


# Lightweight model for migration
class Permission(Base):
    __tablename__ = 'permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(150), unique=True, nullable=False)
    display_name = sa.Column(sa.String(200))
    description = sa.Column(sa.Text)
    resource = sa.Column(sa.String(50))
    action = sa.Column(sa.String(50))
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)


def upgrade() -> None:
    """Add 10 new permissions for approval workflow and member management."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("ADDING NEW PERMISSIONS")
        print("="*80)

        new_permissions = [
            # Content Approval Workflow (4 permissions)
            {
                "name": "content.submit_for_review",
                "display_name": "Submit Content for Review",
                "description": "Submit content for review by content reviewers",
                "resource": "content",
                "action": "submit_for_review"
            },
            {
                "name": "content.approve",
                "display_name": "Approve Content",
                "description": "Approve content submitted for review",
                "resource": "content",
                "action": "approve"
            },
            {
                "name": "content.reject",
                "display_name": "Reject Content",
                "description": "Reject content and request changes",
                "resource": "content",
                "action": "reject"
            },
            {
                "name": "content.publish",
                "display_name": "Publish Content",
                "description": "Publish approved content",
                "resource": "content",
                "action": "publish"
            },

            # Workspace Management (2 permissions)
            {
                "name": "workspace.transfer_ownership",
                "display_name": "Transfer Workspace Ownership",
                "description": "Transfer ownership of workspace to another user",
                "resource": "workspace",
                "action": "transfer_ownership"
            },
            {
                "name": "workspace.manage_billing",
                "display_name": "Manage Workspace Billing",
                "description": "Manage subscription and billing for workspace",
                "resource": "workspace",
                "action": "manage_billing"
            },

            # Member Management (4 permissions)
            {
                "name": "member.read",
                "display_name": "View Workspace Members",
                "description": "View list of workspace members",
                "resource": "member",
                "action": "read"
            },
            {
                "name": "member.invite",
                "display_name": "Invite Members",
                "description": "Invite new members to workspace",
                "resource": "member",
                "action": "invite"
            },
            {
                "name": "member.remove",
                "display_name": "Remove Members",
                "description": "Remove members from workspace",
                "resource": "member",
                "action": "remove"
            },
            {
                "name": "member.update_role",
                "display_name": "Update Member Roles",
                "description": "Change roles of workspace members",
                "resource": "member",
                "action": "update_role"
            },
        ]

        created_count = 0
        skipped_count = 0

        for perm_data in new_permissions:
            # Check if permission already exists
            existing = session.query(Permission).filter_by(
                name=perm_data["name"]
            ).first()

            if existing:
                print(f"  ⊘ Permission '{perm_data['name']}' already exists, skipping")
                skipped_count += 1
                continue

            # Create new permission
            perm = Permission(
                id=uuid.uuid4(),
                name=perm_data["name"],
                display_name=perm_data["display_name"],
                description=perm_data["description"],
                resource=perm_data["resource"],
                action=perm_data["action"],
                created_at=datetime.now(timezone.utc)
            )
            session.add(perm)
            created_count += 1
            print(f"  ✓ Created permission: {perm_data['name']}")

        session.commit()

        print("\n" + "="*80)
        print(f"✓ PERMISSIONS MIGRATION COMPLETE!")
        print(f"  Created: {created_count} new permissions")
        print(f"  Skipped: {skipped_count} existing permissions")
        print(f"  Total: {created_count + skipped_count} permissions processed")
        print("="*80 + "\n")

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Remove the 10 new permissions."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("REMOVING APPROVAL WORKFLOW PERMISSIONS")
        print("="*80)

        permission_names = [
            "content.submit_for_review",
            "content.approve",
            "content.reject",
            "content.publish",
            "workspace.transfer_ownership",
            "workspace.manage_billing",
            "member.read",
            "member.invite",
            "member.remove",
            "member.update_role"
        ]

        deleted_count = 0
        for perm_name in permission_names:
            perm = session.query(Permission).filter_by(name=perm_name).first()
            if perm:
                # Note: role_permissions will cascade delete automatically
                session.delete(perm)
                deleted_count += 1
                print(f"  ✓ Deleted permission: {perm_name}")
            else:
                print(f"  ⊘ Permission not found: {perm_name}")

        session.commit()

        print("\n" + "="*80)
        print(f"✓ DOWNGRADE COMPLETE!")
        print(f"  Deleted: {deleted_count} permissions")
        print("="*80 + "\n")

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Downgrade failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()
