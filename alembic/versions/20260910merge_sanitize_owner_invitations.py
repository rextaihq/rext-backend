"""Merge heads and sanitize pending workspace_owner invitations to editor

Revision ID: 20260910mrgowner
Revises: 20260904rbacfloor, 20260907emailresend
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260910mrgowner"
down_revision: Union[str, Sequence[str], None] = "6f99c7701ed0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "roles" not in table_names:
        print("Roles table does not exist; skipping role sanitization.")
        return

    # 1. Resolve role IDs for workspace owner and editor dynamically across staging/production DBs
    owner_roles = bind.execute(
        sa.text("SELECT id FROM roles WHERE LOWER(name) IN ('workspace_owner', 'owner')")
    ).fetchall()
    owner_role_ids = [row[0] for row in owner_roles]

    editor_role = bind.execute(
        sa.text(
            "SELECT id FROM roles WHERE LOWER(name) IN ('editor', 'workspace_editor') ORDER BY id LIMIT 1"
        )
    ).fetchone()
    editor_role_id = editor_role[0] if editor_role else None

    if not owner_role_ids:
        print("No workspace owner roles found in database; nothing to sanitize.")
        return

    # 2. Sanitize pending user invitations
    if "user_invitations" in table_names:
        if editor_role_id:
            # Dynamically convert any pending owner invitations to editor
            res_invites = bind.execute(
                sa.text("""
                    UPDATE user_invitations
                    SET role_id = :editor_id
                    WHERE role_id IN :owner_ids
                      AND LOWER(status) = 'pending'
                """).bindparams(sa.bindparam("owner_ids", expanding=True)),
                {"editor_id": editor_role_id, "owner_ids": owner_role_ids},
            )
            print(
                f"Updated {res_invites.rowcount} pending workspace_owner invitation(s) to 'editor'"
            )
        else:
            # If no editor role exists in this database environment, revoke pending owner invitations
            res_invites = bind.execute(
                sa.text("""
                    UPDATE user_invitations
                    SET status = 'revoked'
                    WHERE role_id IN :owner_ids
                      AND LOWER(status) = 'pending'
                """).bindparams(sa.bindparam("owner_ids", expanding=True)),
                {"owner_ids": owner_role_ids},
            )
            print(
                f"Revoked {res_invites.rowcount} pending workspace_owner invitation(s) because no editor role was found"
            )

    # 3. Sanitize user_roles to ensure non-creators do not hold workspace_owner
    if "user_roles" in table_names and "workspace" in table_names and editor_role_id:
        # Step A: Delete duplicate role rows if the non-creator already has an editor role in that workspace
        bind.execute(
            sa.text("""
                DELETE FROM user_roles
                WHERE role_id IN :owner_ids
                  AND workspace_id IS NOT NULL
                  AND user_id NOT IN (
                      SELECT user_id FROM workspace WHERE workspace.id = user_roles.workspace_id
                  )
                  AND EXISTS (
                      SELECT 1 FROM user_roles ur2
                      WHERE ur2.user_id = user_roles.user_id
                        AND ur2.workspace_id = user_roles.workspace_id
                        AND ur2.role_id = :editor_id
                  )
            """).bindparams(sa.bindparam("owner_ids", expanding=True)),
            {"editor_id": editor_role_id, "owner_ids": owner_role_ids},
        )

        # Step B: Demote any remaining non-creator workspace_owner assignments to editor
        res_roles = bind.execute(
            sa.text("""
                UPDATE user_roles
                SET role_id = :editor_id
                WHERE role_id IN :owner_ids
                  AND workspace_id IS NOT NULL
                  AND user_id NOT IN (
                      SELECT user_id FROM workspace WHERE workspace.id = user_roles.workspace_id
                  )
            """).bindparams(sa.bindparam("owner_ids", expanding=True)),
            {"editor_id": editor_role_id, "owner_ids": owner_role_ids},
        )
        print(f"Demoted {res_roles.rowcount} non-creator workspace_owner assignment(s) to 'editor'")


def downgrade() -> None:
    pass
