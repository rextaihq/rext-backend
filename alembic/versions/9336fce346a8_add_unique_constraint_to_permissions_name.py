"""add_unique_constraints_to_permissions_and_roles_name

Add missing unique constraints to permissions.name and roles.name columns.
This is required for ON CONFLICT clauses in subsequent migrations.

Revision ID: 9336fce346a8
Revises: 9336fce346a7
Create Date: 2025-10-25 14:21:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9336fce346a8'
down_revision: Union[str, Sequence[str], None] = '9336fce346a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraints to permissions.name and roles.name"""
    conn = op.get_bind()

    # ========================================================================
    # STEP 1: Handle permissions table
    # ========================================================================
    print("\n=== Checking permissions table ===")
    result = conn.execute(sa.text("""
        SELECT name, COUNT(*) as count
        FROM permissions
        GROUP BY name
        HAVING COUNT(*) > 1
    """))

    duplicates = list(result)
    if duplicates:
        print("⚠️  WARNING: Found duplicate permission names:")
        for row in duplicates:
            print(f"  - {row.name}: {row.count} occurrences")
        print("\nRemoving duplicates (keeping the oldest)...")

        # Remove duplicates, keeping the oldest one
        conn.execute(sa.text("""
            DELETE FROM permissions a USING permissions b
            WHERE a.id > b.id
              AND a.name = b.name
        """))
        print("✅ Duplicates removed")

    # Add unique constraint to permissions.name
    print("Adding unique constraint on permissions.name...")
    op.create_unique_constraint(
        'uq_permissions_name',
        'permissions',
        ['name']
    )
    print("✅ Unique constraint added to permissions.name")

    # ========================================================================
    # STEP 2: Handle roles table
    # ========================================================================
    print("\n=== Checking roles table ===")
    result = conn.execute(sa.text("""
        SELECT name, COUNT(*) as count
        FROM roles
        GROUP BY name
        HAVING COUNT(*) > 1
    """))

    duplicates = list(result)
    if duplicates:
        print("⚠️  WARNING: Found duplicate role names:")
        for row in duplicates:
            print(f"  - {row.name}: {row.count} occurrences")
        print("\nRemoving duplicates (keeping the oldest)...")

        # Remove duplicates, keeping the oldest one
        conn.execute(sa.text("""
            DELETE FROM roles a USING roles b
            WHERE a.id > b.id
              AND a.name = b.name
        """))
        print("✅ Duplicates removed")

    # Add unique constraint to roles.name
    print("Adding unique constraint on roles.name...")
    op.create_unique_constraint(
        'uq_roles_name',
        'roles',
        ['name']
    )
    print("✅ Unique constraint added to roles.name")
    print("\n✅ All unique constraints added successfully!")


def downgrade() -> None:
    """Remove unique constraints from permissions.name and roles.name"""
    op.drop_constraint('uq_roles_name', 'roles', type_='unique')
    op.drop_constraint('uq_permissions_name', 'permissions', type_='unique')
