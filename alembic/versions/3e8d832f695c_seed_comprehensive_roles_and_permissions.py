"""seed_comprehensive_roles_and_permissions

Revision ID: 3e8d832f695c
Revises: 2cc855f144c1
Create Date: 2025-10-02 11:55:23.991612

"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision: str = '3e8d832f695c'
down_revision: Union[str, Sequence[str], None] = '2cc855f144c1'
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
    # Note: is_workspace_role does not exist at this point in migration history
    created_at = sa.Column(sa.TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = sa.Column(sa.TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    permission_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)


def upgrade() -> None:
    """Seed comprehensive roles and permissions."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Define all permissions (37 total)
    permissions_data = [
        # User permissions (5)
        {"name": "user.read", "display_name": "Read Users", "description": "View user information", "resource": "user", "action": "read"},
        {"name": "user.create", "display_name": "Create Users", "description": "Create new users", "resource": "user", "action": "create"},
        {"name": "user.update", "display_name": "Update Users", "description": "Update user information", "resource": "user", "action": "update"},
        {"name": "user.delete", "display_name": "Delete Users", "description": "Delete users", "resource": "user", "action": "delete"},
        {"name": "user.manage_roles", "display_name": "Manage User Roles", "description": "Assign/revoke user roles", "resource": "user", "action": "manage_roles"},

        # Role permissions (5)
        {"name": "role.read", "display_name": "Read Roles", "description": "View roles", "resource": "role", "action": "read"},
        {"name": "role.create", "display_name": "Create Roles", "description": "Create new roles", "resource": "role", "action": "create"},
        {"name": "role.update", "display_name": "Update Roles", "description": "Update roles", "resource": "role", "action": "update"},
        {"name": "role.delete", "display_name": "Delete Roles", "description": "Delete roles", "resource": "role", "action": "delete"},
        {"name": "role.manage_permissions", "display_name": "Manage Role Permissions", "description": "Assign/revoke permissions to roles", "resource": "role", "action": "manage_permissions"},

        # Permission permissions (4)
        {"name": "permission.read", "display_name": "Read Permissions", "description": "View permissions", "resource": "permission", "action": "read"},
        {"name": "permission.create", "display_name": "Create Permissions", "description": "Create new permissions", "resource": "permission", "action": "create"},
        {"name": "permission.update", "display_name": "Update Permissions", "description": "Update permissions", "resource": "permission", "action": "update"},
        {"name": "permission.delete", "display_name": "Delete Permissions", "description": "Delete permissions", "resource": "permission", "action": "delete"},

        # Workspace permissions (6)
        {"name": "workspace.read", "display_name": "Read Workspaces", "description": "View workspace information", "resource": "workspace", "action": "read"},
        {"name": "workspace.create", "display_name": "Create Workspaces", "description": "Create new workspaces", "resource": "workspace", "action": "create"},
        {"name": "workspace.update", "display_name": "Update Workspaces", "description": "Update workspace information", "resource": "workspace", "action": "update"},
        {"name": "workspace.delete", "display_name": "Delete Workspaces", "description": "Delete workspaces", "resource": "workspace", "action": "delete"},
        {"name": "workspace.manage_members", "display_name": "Manage Workspace Members", "description": "Add/remove workspace members", "resource": "workspace", "action": "manage_members"},
        {"name": "workspace.invite", "display_name": "Invite to Workspace", "description": "Send workspace invitations", "resource": "workspace", "action": "invite"},

        # Content permissions (4)
        {"name": "content.read", "display_name": "Read Content", "description": "View content", "resource": "content", "action": "read"},
        {"name": "content.create", "display_name": "Create Content", "description": "Create new content", "resource": "content", "action": "create"},
        {"name": "content.update", "display_name": "Update Content", "description": "Update content", "resource": "content", "action": "update"},
        {"name": "content.delete", "display_name": "Delete Content", "description": "Delete content", "resource": "content", "action": "delete"},

        # Topic permissions (4)
        {"name": "topic.read", "display_name": "Read Topics", "description": "View topics", "resource": "topic", "action": "read"},
        {"name": "topic.create", "display_name": "Create Topics", "description": "Create new topics", "resource": "topic", "action": "create"},
        {"name": "topic.update", "display_name": "Update Topics", "description": "Update topics", "resource": "topic", "action": "update"},
        {"name": "topic.delete", "display_name": "Delete Topics", "description": "Delete topics", "resource": "topic", "action": "delete"},

        # Knowledge permissions (4)
        {"name": "knowledge.read", "display_name": "Read Knowledge", "description": "View knowledge items", "resource": "knowledge", "action": "read"},
        {"name": "knowledge.create", "display_name": "Create Knowledge", "description": "Create knowledge items", "resource": "knowledge", "action": "create"},
        {"name": "knowledge.update", "display_name": "Update Knowledge", "description": "Update knowledge items", "resource": "knowledge", "action": "update"},
        {"name": "knowledge.delete", "display_name": "Delete Knowledge", "description": "Delete knowledge items", "resource": "knowledge", "action": "delete"},

        # Subscription permissions (2)
        {"name": "subscription.read", "display_name": "Read Subscriptions", "description": "View subscription information", "resource": "subscription", "action": "read"},
        {"name": "subscription.manage", "display_name": "Manage Subscriptions", "description": "Manage subscription plans and billing", "resource": "subscription", "action": "manage"},

        # Audit log permissions (1)
        {"name": "audit.read", "display_name": "Read Audit Logs", "description": "View audit logs", "resource": "audit", "action": "read"},
    ]

    # Create permissions (idempotent)
    permission_map = {}
    for perm_data in permissions_data:
        exists = session.query(Permission).filter_by(name=perm_data["name"]).first()
        if not exists:
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
            session.flush()
            permission_map[perm_data["name"]] = perm.id
        else:
            permission_map[perm_data["name"]] = exists.id

    session.commit()

    # Define roles (7 total)
    roles_data = [
        {
            "name": "super_admin",
            "display_name": "Super Administrator",
            "description": "Full system access with all permissions",
            "hierarchy_level": 100,
            "permissions": [p["name"] for p in permissions_data]  # All 37 permissions
        },
        {
            "name": "admin",
            "display_name": "Administrator",
            "description": "Administrative access with most permissions",
            "hierarchy_level": 80,
            "permissions": [
                "user.read", "user.create", "user.update", "user.manage_roles",
                "role.read", "permission.read",
                "workspace.read", "workspace.create", "workspace.update", "workspace.manage_members", "workspace.invite",
                "content.read", "content.create", "content.update", "content.delete",
                "topic.read", "topic.create", "topic.update", "topic.delete",
                "knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete",
                "subscription.read", "audit.read"
            ]
        },
        {
            "name": "workspace_owner",
            "display_name": "Workspace Owner",
            "description": "Full control over owned workspaces",
            "hierarchy_level": 60,
            "is_system_role": False,  # Not a platform role
            # Note: is_workspace_role is added in a later migration (3dbd19e83367)
            "permissions": [
                "workspace.read", "workspace.update", "workspace.delete", "workspace.manage_members", "workspace.invite",
                "content.read", "content.create", "content.update", "content.delete",
                "topic.read", "topic.create", "topic.update", "topic.delete",
                "knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete",
                "user.read"
            ]
        },
        {
            "name": "workspace_admin",
            "display_name": "Workspace Administrator",
            "description": "Manage workspace members and content",
            "hierarchy_level": 50,
            "is_system_role": False,  # Not a platform role
            # Note: is_workspace_role is added in a later migration (3dbd19e83367)
            "permissions": [
                "workspace.read", "workspace.update", "workspace.manage_members", "workspace.invite",
                "content.read", "content.create", "content.update", "content.delete",
                "topic.read", "topic.create", "topic.update", "topic.delete",
                "knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete",
                "user.read"
            ]
        },
        {
            "name": "editor",
            "display_name": "Editor",
            "description": "Create and edit content",
            "hierarchy_level": 30,
            "is_system_role": False,  # Not a platform role
            # Note: is_workspace_role is added in a later migration (3dbd19e83367)
            "permissions": [
                "workspace.read",
                "content.read", "content.create", "content.update",
                "topic.read", "topic.create", "topic.update",
                "knowledge.read", "knowledge.create", "knowledge.update",
                "user.read"
            ]
        },
        {
            "name": "viewer",
            "display_name": "Viewer",
            "description": "Read-only access to content",
            "hierarchy_level": 10,
            "is_system_role": False,  # Not a platform role
            # Note: is_workspace_role is added in a later migration (3dbd19e83367)
            "permissions": [
                "workspace.read",
                "content.read",
                "topic.read",
                "knowledge.read",
                "user.read"
            ]
        },
        {
            "name": "user",
            "display_name": "User",
            "description": "Default role for regular users",
            "hierarchy_level": 1,
            "permissions": [
                "workspace.read", "workspace.create",
                "content.read",
                "topic.read",
                "knowledge.read"
            ]
        }
    ]

    # Create roles and assign permissions
    for role_data in roles_data:
        exists = session.query(Role).filter_by(name=role_data["name"]).first()
        if not exists:
            role = Role(
                id=uuid.uuid4(),
                name=role_data["name"],
                display_name=role_data["display_name"],
                description=role_data["description"],
                hierarchy_level=role_data["hierarchy_level"],
                is_system_role=role_data.get("is_system_role", True),  # Default to True if not specified
                # Note: is_workspace_role is added in a later migration (3dbd19e83367)
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            session.add(role)
            session.flush()

            # Assign permissions to role
            for perm_name in role_data["permissions"]:
                if perm_name in permission_map:
                    role_perm = RolePermission(
                        id=uuid.uuid4(),
                        role_id=role.id,
                        permission_id=permission_map[perm_name],
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(role_perm)

    session.commit()


def downgrade() -> None:
    """Remove seeded data."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Delete role_permissions for system roles
    system_roles = session.query(Role).filter_by(is_system_role=True).all()
    for role in system_roles:
        session.query(RolePermission).filter_by(role_id=role.id).delete()

    # Delete system roles
    session.query(Role).filter_by(is_system_role=True).delete()

    # Delete all permissions
    session.query(Permission).delete()

    session.commit()
