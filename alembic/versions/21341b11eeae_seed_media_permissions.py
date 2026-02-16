"""seed_media_permissions

Adds media management permissions for RBAC:
- media.create (upload media files)
- media.view (view media files)
- media.update (update media metadata)
- media.delete (delete media files)

Updates role-permission mappings for media access control.

Revision ID: 21341b11eeae
Revises: e6ff3a3a0bb5
Create Date: 2025-10-12 23:49:58.332376

"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision: str = '21341b11eeae'
down_revision: Union[str, Sequence[str], None] = 'e6ff3a3a0bb5'
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
    created_at = sa.Column(sa.TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = sa.Column(sa.TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    permission_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)


def upgrade() -> None:
    """Add media permissions and update role mappings."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Define media permissions
    media_permissions = [
        {
            "name": "media.create",
            "display_name": "Upload Media",
            "description": "Upload media files (images, documents, videos) to workspace",
            "resource": "media",
            "action": "create"
        },
        {
            "name": "media.view",
            "display_name": "View Media",
            "description": "View and list media files in workspace",
            "resource": "media",
            "action": "view"
        },
        {
            "name": "media.update",
            "display_name": "Update Media",
            "description": "Update media metadata (title, description, tags, etc.)",
            "resource": "media",
            "action": "update"
        },
        {
            "name": "media.delete",
            "display_name": "Delete Media",
            "description": "Delete media files from workspace",
            "resource": "media",
            "action": "delete"
        }
    ]

    # Insert permissions
    permission_ids = {}
    for perm in media_permissions:
        # Check if permission already exists
        existing = session.query(Permission).filter_by(name=perm["name"]).first()
        if existing:
            permission_ids[perm["name"]] = existing.id
            continue

        perm_id = uuid.uuid4()
        permission_ids[perm["name"]] = perm_id

        new_perm = Permission(
            id=perm_id,
            name=perm["name"],
            display_name=perm["display_name"],
            description=perm["description"],
            resource=perm["resource"],
            action=perm["action"],
            created_at=datetime.now(timezone.utc)
        )
        session.add(new_perm)

    session.commit()

    # Assign permissions to roles
    # Role hierarchy: admin > manager > editor > contributor > viewer

    role_permission_mappings = {
        "admin": ["media.create", "media.view", "media.update", "media.delete"],
        "manager": ["media.create", "media.view", "media.update", "media.delete"],
        "editor": ["media.create", "media.view", "media.update"],
        "contributor": ["media.create", "media.view"],
        "viewer": ["media.view"]
    }

    for role_name, permission_names in role_permission_mappings.items():
        role = session.query(Role).filter_by(name=role_name).first()
        if not role:
            continue

        for perm_name in permission_names:
            perm_id = permission_ids.get(perm_name)
            if not perm_id:
                continue

            # Check if role-permission mapping already exists
            existing_mapping = session.query(RolePermission).filter_by(
                role_id=role.id,
                permission_id=perm_id
            ).first()
            if existing_mapping:
                continue

            # Create role-permission mapping
            role_perm = RolePermission(
                id=uuid.uuid4(),
                role_id=role.id,
                permission_id=perm_id,
                created_at=datetime.now(timezone.utc)
            )
            session.add(role_perm)

    session.commit()


def downgrade() -> None:
    """Remove media permissions."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Delete media permissions (CASCADE will remove role_permissions)
    session.query(Permission).filter(Permission.resource == "media").delete()
    session.commit()
