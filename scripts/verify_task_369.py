import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from src.api.database.async_database import get_async_db
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.role_permissions import RolePermission


async def verify():
    print("Verifying TASK-369 implementation...")

    async for db in get_async_db():
        # Check permissions exist
        resend_perm = await db.execute(select(Permission).where(Permission.name == "email.resend"))
        audit_write_perm = await db.execute(
            select(Permission).where(Permission.name == "audit.write")
        )

        p1 = resend_perm.scalar_one_or_none()
        p2 = audit_write_perm.scalar_one_or_none()

        if p1:
            print(f"✅ Permission 'email.resend' exists (ID: {p1.id})")
        else:
            print("❌ Permission 'email.resend' NOT found")

        if p2:
            print(f"✅ Permission 'audit.write' exists (ID: {p2.id})")
        else:
            print("❌ Permission 'audit.write' NOT found")

        # Check assignments to super_admin and admin
        for role_name in ["super_admin", "admin"]:
            role_res = await db.execute(select(Role).where(Role.name == role_name))
            role = role_res.scalar_one_or_none()

            if not role:
                print(f"⚠️ Role '{role_name}' NOT found in database")
                continue

            print(f"\nChecking role: {role_name}")

            for p, name in [(p1, "email.resend"), (p2, "audit.write")]:
                if not p:
                    continue

                rp_res = await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id, RolePermission.permission_id == p.id
                    )
                )
                if rp_res.scalar_one_or_none():
                    print(f"  ✅ Permission '{name}' is assigned")
                else:
                    print(f"  ❌ Permission '{name}' is NOT assigned")

        break


if __name__ == "__main__":
    asyncio.run(verify())
