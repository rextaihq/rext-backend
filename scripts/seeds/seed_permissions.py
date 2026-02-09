"""Seed RBAC permissions. Consolidates seed006-seed009 into a single idempotent script."""

import asyncio
from sqlalchemy import text

from scripts.seeds.base import get_seed_session, utc_now


# Consolidate all permissions from seed006-seed009 here
# Each permission: (name, display_name, description, resource, action)
PERMISSIONS = [
    # Add all permission definitions from seed006-seed009 here
    # Example:
    # ("content:create", "Create Content", "Allow creating content", "content", "create"),
    # ... (extract from actual seed migration files)
]


async def seed_permissions():
    """Seed RBAC permissions (idempotent — skips existing by name)."""
    async with get_seed_session() as session:
        created = 0
        skipped = 0

        for name, display_name, description, resource, action in PERMISSIONS:
            result = await session.execute(
                text("SELECT id FROM permissions WHERE name = :name"),
                {"name": name},
            )
            if result.fetchone():
                skipped += 1
                continue

            now = utc_now()
            await session.execute(
                text("""
                    INSERT INTO permissions (id, name, display_name, description, resource, action, created_at)
                    VALUES (gen_random_uuid(), :name, :display_name, :description, :resource, :action, :created_at)
                """),
                {
                    "name": name,
                    "display_name": display_name,
                    "description": description,
                    "resource": resource,
                    "action": action,
                    "created_at": now,
                },
            )
            created += 1

        print(f"Permissions: {created} created, {skipped} already existed")


if __name__ == "__main__":
    asyncio.run(seed_permissions())
