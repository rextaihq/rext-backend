"""seed_additional_rbac_permissions

Revision ID: seed006
Revises: seed005
Create Date: 2025-10-06 00:00:00.000000

Adds fine-grained permissions for Phase 2 RBAC implementation:
- content.publish (publish content to production)
- topic.approve (approve topics for content generation)
- member.invite (invite members to workspace)
- member.remove (remove members from workspace)

Updates role-permission mappings for more granular access control.
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime

# revision identifiers, used by Alembic.
revision: str = 'seed006'
down_revision: Union[str, Sequence[str], None] = 'seed005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


# Lightweight models for seeding
class Permission(Base):
    __tablename__ = 'permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(150), unique=True, nullable=False)
    display_name = sa.Column(sa.String(200))
    description = sa.Column(sa.Text)
    resource = sa.Column(sa.String(50))
    action = sa.Column(sa.String(50))
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)


class Role(Base):
    __tablename__ = 'roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)
    display_name = sa.Column(sa.String(150), nullable=False)
    description = sa.Column(sa.Text)
    hierarchy_level = sa.Column(sa.Integer, default=0)
    is_system_role = sa.Column(sa.Boolean, default=True)
    created_at = sa.Column(sa.TIMESTAMP, default=datetime.utcnow)
    updated_at = sa.Column(sa.TIMESTAMP, default=datetime.utcnow)


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    permission_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)


def upgrade() -> None:
    """Add fine-grained permissions and update role mappings."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Define new permissions
    new_permissions = [
        {
            "name": "content.publish",
            "display_name": "Publish Content",
            "description": "Publish content to production",
            "resource": "content",
            "action": "publish"
        },
        {
            "name": "topic.approve",
            "display_name": "Approve Topics",
            "description": "Approve topics for content generation",
            "resource": "topic",
            "action": "approve"
        },
        {
            "name": "member.invite",
            "display_name": "Invite Members",
            "description": "Invite members to workspace",
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
            "name": "member.read",
            "display_name": "View Members",
            "description": "View workspace members",
            "resource": "member",
            "action": "read"
        },
        {
            "name": "member.update",
            "display_name": "Update Members",
            "description": "Update member roles and permissions",
            "resource": "member",
            "action": "update"
        },
    ]

    # Create new permissions (idempotent)
    permission_map = {}
    for perm_data in new_permissions:
        exists = session.query(Permission).filter_by(name=perm_data["name"]).first()
        if not exists:
            perm = Permission(
                id=uuid.uuid4(),
                name=perm_data["name"],
                display_name=perm_data["display_name"],
                description=perm_data["description"],
                resource=perm_data["resource"],
                action=perm_data["action"],
                created_at=datetime.utcnow()
            )
            session.add(perm)
            session.flush()
            permission_map[perm_data["name"]] = perm.id
            print(f"✅ Created permission: {perm_data['name']}")
        else:
            permission_map[perm_data["name"]] = exists.id
            print(f"ℹ️  Permission already exists: {perm_data['name']}")

    session.commit()

    # Update role-permission mappings
    # Define which roles get the new permissions
    role_permission_updates = {
        "super_admin": [
            "content.publish", "topic.approve", "member.invite",
            "member.remove", "member.read", "member.update"
        ],
        "admin": [
            "content.publish", "topic.approve", "member.invite",
            "member.remove", "member.read", "member.update"
        ],
        "workspace_owner": [
            "content.publish", "topic.approve", "member.invite",
            "member.remove", "member.read", "member.update"
        ],
        "workspace_admin": [
            "content.publish", "topic.approve", "member.invite",
            "member.remove", "member.read", "member.update"
        ],
        "editor": [
            "content.publish", "topic.approve", "member.read"
        ],
        "viewer": [
            "member.read"
        ],
        "user": [
            "member.read"
        ]
    }

    # Assign new permissions to roles
    for role_name, permission_names in role_permission_updates.items():
        role = session.query(Role).filter_by(name=role_name).first()
        if not role:
            print(f"⚠️  Role not found: {role_name}")
            continue

        for perm_name in permission_names:
            # Get permission from map or query
            if perm_name in permission_map:
                perm_id = permission_map[perm_name]
            else:
                perm = session.query(Permission).filter_by(name=perm_name).first()
                if not perm:
                    print(f"⚠️  Permission not found: {perm_name}")
                    continue
                perm_id = perm.id

            # Check if mapping already exists
            exists = session.query(RolePermission).filter_by(
                role_id=role.id,
                permission_id=perm_id
            ).first()

            if not exists:
                role_perm = RolePermission(
                    id=uuid.uuid4(),
                    role_id=role.id,
                    permission_id=perm_id,
                    created_at=datetime.utcnow()
                )
                session.add(role_perm)
                print(f"✅ Assigned {perm_name} to {role_name}")
            else:
                print(f"ℹ️  {role_name} already has {perm_name}")

    session.commit()
    print("\n✅ Additional RBAC permissions seeded successfully!")


def downgrade() -> None:
    """Remove added permissions and role mappings."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Remove permissions (cascade will remove role_permissions)
    permission_names = [
        "content.publish",
        "topic.approve",
        "member.invite",
        "member.remove",
        "member.read",
        "member.update"
    ]

    for perm_name in permission_names:
        perm = session.query(Permission).filter_by(name=perm_name).first()
        if perm:
            # Delete role_permission mappings first
            session.query(RolePermission).filter_by(permission_id=perm.id).delete()
            # Then delete permission
            session.delete(perm)
            print(f"🗑️  Removed permission: {perm_name}")

    session.commit()
    print("\n✅ Additional RBAC permissions removed successfully!")
