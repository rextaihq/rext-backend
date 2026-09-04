"""add is_system to permissions

Revision ID: 20260904isperm
Revises: 20260901ipallow
Create Date: 2026-09-04

Marks every permission that already exists (i.e. everything seeded by
scripts/seeds/seed_permissions.py) as a protected system permission, so
PermissionService.delete_permission can refuse to delete it even once it is
unassigned from every role - the same protection roles already get via
is_system_role (see RoleService._is_protected_role). Permissions created
afterwards via the admin "create permission" flow default to False and stay
deletable.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260904isperm"
down_revision: Union[str, Sequence[str], None] = "20260901ipallow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "permissions",
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute("UPDATE permissions SET is_system = true")


def downgrade() -> None:
    op.drop_column("permissions", "is_system")
