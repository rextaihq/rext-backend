"""Seed the super admin named by the environment, if that account does not exist yet."""

import asyncio
import os
from uuid import uuid4

from sqlalchemy import text

from scripts.seeds.base import get_seed_session, utc_now
from src.api.security.token_utils import hash_password


async def seed_super_admin():
    """Create the SUPER_ADMIN_EMAIL account with the super_admin role.

    SUPER_ADMIN_PASSWORD is its first password and SUPER_ADMIN_FIRST_NAME and
    SUPER_ADMIN_LAST_NAME its name. An account that already exists is left as it
    is, password included.
    """
    email = os.getenv("SUPER_ADMIN_EMAIL")
    password = os.getenv("SUPER_ADMIN_PASSWORD")
    if not email or not password:
        print("Super admin: SUPER_ADMIN_EMAIL or SUPER_ADMIN_PASSWORD is not set, skipped")
        return
    name = f"{os.getenv('SUPER_ADMIN_FIRST_NAME', 'Super')} {os.getenv('SUPER_ADMIN_LAST_NAME', 'Admin')}"

    async with get_seed_session() as session:
        if await session.scalar(text("SELECT 1 FROM users WHERE email = :email"), {"email": email}):
            print("Super admin: already exists")
            return
        role_id = await session.scalar(text("SELECT id FROM roles WHERE name = 'super_admin'"))
        if role_id is None:
            raise RuntimeError("the super_admin role is missing: seed the roles first")

        user_id, now = uuid4(), utc_now()
        await session.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name, display_name, status, "
                "email_verified, email_verified_at, language, timezone, created_at, updated_at) "
                "VALUES (:id, :email, :password_hash, :name, :name, 'active', true, :now, 'en', 'UTC', "
                ":now, :now)"
            ),
            {
                "id": user_id,
                "email": email,
                "password_hash": hash_password(password),
                "name": name,
                "now": now,
            },
        )
        await session.execute(
            text(
                "INSERT INTO user_roles (id, user_id, role_id, workspace_id, assigned_by_user_id, "
                "is_primary, assigned_at) VALUES (:id, :user_id, :role_id, NULL, :user_id, true, :now)"
            ),
            {"id": uuid4(), "user_id": user_id, "role_id": role_id, "now": now},
        )
        print("Super admin: created")


if __name__ == "__main__":
    asyncio.run(seed_super_admin())
