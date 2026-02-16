"""cleanup_post_content_reviewer_removal

Clean up after content_reviewer role removal:
1. Remove approval permissions from editor role (editors should not approve their own content)
2. Remove duplicate content.submit_review permission (keep content.submit_for_review)
3. Ensure workspace_admin and workspace_owner have approval permissions

SECURITY FIX: Editors should only submit content for review, not approve it.
This ensures separation of duties in the content approval workflow.

Revision ID: 9336fce346a7
Revises: 9161a9c82f14
Create Date: 2025-10-24 15:38:59.624709

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm, text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
import uuid

# revision identifiers, used by Alembic.
revision: str = '9336fce346a7'
down_revision: Union[str, Sequence[str], None] = '9161a9c82f14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


class Role(Base):
    __tablename__ = 'roles'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100))


class Permission(Base):
    __tablename__ = 'permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(150))
    display_name = sa.Column(sa.String(200))


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    role_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    permission_id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True))
    created_at = sa.Column(sa.TIMESTAMP)


def upgrade() -> None:
    """Clean up permissions after content_reviewer removal."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("POST-CONTENT_REVIEWER CLEANUP")
        print("="*80)

        # STEP 1: Remove approval permissions from editor role
        print("\n→ Step 1: Removing approval permissions from editor role")
        print("   (Editors should submit for review, not approve their own content)")

        editor_role = session.query(Role).filter_by(name='editor').first()
        if editor_role:
            approval_perms = session.query(Permission).filter(
                Permission.name.in_(['content.approve', 'content.reject'])
            ).all()

            removed_count = 0
            for perm in approval_perms:
                deleted = session.query(RolePermission).filter_by(
                    role_id=editor_role.id,
                    permission_id=perm.id
                ).delete(synchronize_session=False)

                if deleted > 0:
                    removed_count += deleted
                    print(f"  ✓ Removed {perm.name} from editor")

            if removed_count == 0:
                print(f"  ✓ Editor already has no approval permissions")
        else:
            print(f"  ⚠️  Editor role not found")

        # STEP 2: Ensure workspace_admin and workspace_owner have approval permissions
        print("\n→ Step 2: Ensuring workspace_admin and workspace_owner have approval permissions")

        approval_permissions = ['content.approve', 'content.reject']
        admin_roles = ['workspace_admin', 'workspace_owner']

        for role_name in admin_roles:
            role = session.query(Role).filter_by(name=role_name).first()
            if not role:
                print(f"  ⚠️  Role '{role_name}' not found, skipping...")
                continue

            for perm_name in approval_permissions:
                perm = session.query(Permission).filter_by(name=perm_name).first()
                if not perm:
                    print(f"  ⚠️  Permission '{perm_name}' not found, skipping...")
                    continue

                # Check if already assigned
                existing = session.query(RolePermission).filter_by(
                    role_id=role.id,
                    permission_id=perm.id
                ).first()

                if existing:
                    print(f"  ✓ {role_name} already has {perm_name}")
                else:
                    # Assign permission
                    rp = RolePermission(
                        id=uuid.uuid4(),
                        role_id=role.id,
                        permission_id=perm.id,
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(rp)
                    print(f"  ✓ Assigned {perm_name} to {role_name}")

        # STEP 3: Remove duplicate content.submit_review permission
        print("\n→ Step 3: Removing duplicate content.submit_review permission")

        duplicate = session.query(Permission).filter_by(name='content.submit_review').first()
        preferred = session.query(Permission).filter_by(name='content.submit_for_review').first()

        if duplicate and preferred:
            # First, migrate any role_permissions using duplicate to use preferred
            migrated = 0
            duplicate_assignments = session.query(RolePermission).filter_by(
                permission_id=duplicate.id
            ).all()

            for assignment in duplicate_assignments:
                # Check if role already has the preferred permission
                has_preferred = session.query(RolePermission).filter_by(
                    role_id=assignment.role_id,
                    permission_id=preferred.id
                ).first()

                if not has_preferred:
                    # Update to use preferred permission
                    assignment.permission_id = preferred.id
                    migrated += 1
                else:
                    # Delete duplicate (role already has preferred)
                    session.delete(assignment)

            # Delete the duplicate permission
            session.delete(duplicate)
            print(f"  ✓ Migrated {migrated} role assignments to content.submit_for_review")
            print(f"  ✓ Removed duplicate permission: content.submit_review")
        elif duplicate and not preferred:
            print(f"  ⚠️  Found duplicate but not preferred, renaming...")
            duplicate.name = 'content.submit_for_review'
            duplicate.display_name = 'Submit Content for Review'
            print(f"  ✓ Renamed content.submit_review → content.submit_for_review")
        else:
            print(f"  ✓ No duplicate permission found (already cleaned)")

        # STEP 4: Verify final state
        print("\n→ Step 4: Verifying final permission assignments")

        # Check editor does NOT have approval permissions
        editor_role = session.query(Role).filter_by(name='editor').first()
        if editor_role:
            editor_approvals = session.execute(text("""
                SELECT p.name
                FROM role_permissions rp
                JOIN permissions p ON rp.permission_id = p.id
                WHERE rp.role_id = :role_id
                  AND p.name IN ('content.approve', 'content.reject')
            """), {"role_id": str(editor_role.id)}).fetchall()

            if len(editor_approvals) > 0:
                print(f"  ❌ ERROR: Editor still has approval permissions!")
                for perm in editor_approvals:
                    print(f"     - {perm[0]}")
                raise Exception("Editor should not have approval permissions")
            else:
                print(f"  ✓ Editor correctly has NO approval permissions")

        # Check admin roles HAVE approval permissions
        for role_name in admin_roles:
            role = session.query(Role).filter_by(name=role_name).first()
            if role:
                admin_approvals = session.execute(text("""
                    SELECT p.name
                    FROM role_permissions rp
                    JOIN permissions p ON rp.permission_id = p.id
                    WHERE rp.role_id = :role_id
                      AND p.name IN ('content.approve', 'content.reject')
                """), {"role_id": str(role.id)}).fetchall()

                if len(admin_approvals) == 2:
                    print(f"  ✓ {role_name} has both approval permissions")
                else:
                    print(f"  ⚠️  WARNING: {role_name} missing some approval permissions")

        session.commit()

        print("\n" + "="*80)
        print("✓ POST-CONTENT_REVIEWER CLEANUP COMPLETE!")
        print("")
        print("Summary:")
        print("  - Editor role: Can submit for review, CANNOT approve/reject")
        print("  - Admin roles: Can approve/reject content")
        print("  - Duplicate permission removed: content.submit_review")
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
    """Restore previous state (not recommended).

    This would restore approval permissions to editor role,
    which is a security issue (editors approving their own content).
    """
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    try:
        print("\n" + "="*80)
        print("DOWNGRADE: RESTORING EDITOR APPROVAL PERMISSIONS")
        print("="*80)
        print("\n⚠️  WARNING: This restores approval permissions to editor role")
        print("   This is NOT RECOMMENDED as it allows editors to approve their own content.\n")

        # Restore approval permissions to editor
        editor_role = session.query(Role).filter_by(name='editor').first()
        if editor_role:
            approval_perms = session.query(Permission).filter(
                Permission.name.in_(['content.approve', 'content.reject'])
            ).all()

            for perm in approval_perms:
                existing = session.query(RolePermission).filter_by(
                    role_id=editor_role.id,
                    permission_id=perm.id
                ).first()

                if not existing:
                    rp = RolePermission(
                        id=uuid.uuid4(),
                        role_id=editor_role.id,
                        permission_id=perm.id,
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(rp)
                    print(f"  ✓ Restored {perm.name} to editor")

        session.commit()
        print("\n" + "="*80)
        print("✓ DOWNGRADE COMPLETE")
        print("="*80 + "\n")

    except Exception as e:
        session.rollback()
        print(f"\n❌ ERROR: Downgrade failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()
