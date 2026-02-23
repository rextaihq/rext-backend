"""add user.impersonate permission

Revision ID: 5a6b7c8d9e0f
Revises: 1f6d82da1298
Create Date: 2026-02-19 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision: str = '5a6b7c8d9e0f'
down_revision: Union[str, Sequence[str], None] = '1f6d82da1298'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()

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

class RolePermission(Base):
    __tablename__ = 'role_permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    permission_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)

def upgrade() -> None:
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # 1. Add user.impersonate permission
    perm_name = "user.impersonate"
    perm_exists = session.query(Permission).filter_by(name=perm_name).first()
    
    if not perm_exists:
        perm = Permission(
            id=uuid.uuid4(),
            name=perm_name,
            display_name="Impersonate Users",
            description="Allows impersonating other users for support and debugging",
            resource="user",
            action="impersonate",
            created_at=datetime.now(timezone.utc)
        )
        session.add(perm)
        session.flush()
        perm_id = perm.id
    else:
        perm_id = perm_exists.id

    # 2. Assign to super_admin role
    super_admin_role = session.query(Role).filter_by(name="super_admin").first()
    if super_admin_role:
        # Check if already assigned
        already_assigned = session.query(RolePermission).filter_by(
            role_id=super_admin_role.id,
            permission_id=perm_id
        ).first()
        
        if not already_assigned:
            role_perm = RolePermission(
                id=uuid.uuid4(),
                role_id=super_admin_role.id,
                permission_id=perm_id,
                created_at=datetime.now(timezone.utc)
            )
            session.add(role_perm)

    session.commit()

def downgrade() -> None:
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    perm = session.query(Permission).filter_by(name="user.impersonate").first()
    if perm:
        # Delete associations first
        session.query(RolePermission).filter_by(permission_id=perm.id).delete()
        # Delete permission
        session.delete(perm)

    session.commit()
