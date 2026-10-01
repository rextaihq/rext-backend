#!/usr/bin/env python3
"""
Database management script for rext-backend

Usage:
    python scripts/db.py reset    - Reset database (drops all data)
    python scripts/db.py migrate  - Run all migrations + setup store
    python scripts/db.py seed     - Reset + migrate + setup store (fresh start)
    python scripts/db.py status   - Check migration status
    python scripts/db.py store    - Setup LangGraph store tables
"""

import asyncio
import sys
import os
import subprocess
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

# Load environment from project root
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
env_path = project_root / ".env"
load_dotenv(env_path)


# Tables owned by the LangGraph Agent Server runtime. They are created and
# migrated automatically by the rext-api server at STARTUP (there is no CLI
# to create them) — per the docs, all access to them must go through the
# Agent Server. Dropping them breaks crons/checkpoints/threads until the
# backend container is restarted, so the reset must never touch them.
LANGGRAPH_TABLES = {
    "assistant",
    "assistant_versions",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
    "checkpoint_delete_queue",
    "cron",
    "run",
    "thread",
    "thread_ttl",
    "store",
    "store_migrations",
    "store_vectors",
    "vector_migrations",
    "schema_migrations",
    "resumable_streams",
    "queue",
}


async def reset_database():
    """Reset the app's tables, preserving LangGraph runtime tables.

    Drops every table in the public schema EXCEPT the LangGraph runtime
    tables (checkpoints, threads, crons, store, ...), plus leftover enum
    types, so alembic can re-run from scratch. Deliberately does NOT use
    `DROP SCHEMA public CASCADE`: that would also destroy the LangGraph
    tables (breaking the running backend until restart) and the pgvector
    extension (which only a superuser can recreate).
    """
    db_url = os.getenv("POSTGRES_URI_CUSTOM")
    if not db_url:
        print("❌ Error: POSTGRES_URI_CUSTOM not set in .env")
        sys.exit(1)

    # Convert to asyncpg URL
    if not db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    print("⚠️  WARNING: This will delete ALL application data in the database!")
    print("   (LangGraph runtime tables are preserved)")
    print(f"Database: {db_url.split('@')[-1]}")  # Show only host/db part

    try:
        engine = create_async_engine(db_url)
        async with engine.begin() as conn:
            # Terminate other open sessions to prevent deadlocks during table drop
            try:
                await conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                    )
                )
            except Exception:
                pass

            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            app_tables = [row[0] for row in result if row[0] not in LANGGRAPH_TABLES]

            for table in app_tables:
                await conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            print(f"✅ Dropped {len(app_tables)} application tables")

            # Drop leftover enum types created by previous migrations so
            # alembic's CREATE TYPE statements don't fail on re-run.
            result = await conn.execute(
                text(
                    "SELECT t.typname FROM pg_type t "
                    "JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = 'public' AND t.typtype = 'e'"
                )
            )
            enum_types = [row[0] for row in result]
            for enum_type in enum_types:
                await conn.execute(text(f'DROP TYPE IF EXISTS "{enum_type}" CASCADE'))
            if enum_types:
                print(f"✅ Dropped {len(enum_types)} enum types")

            print("✅ Database reset successfully")
        await engine.dispose()
        return True
    except Exception as e:
        print(f"❌ Error resetting database: {e}")
        return False


def run_migrations():
    """Run alembic migrations to upgrade to head."""
    print("\n📦 Running migrations...")
    if os.name == "nt":  # Windows
        venv_alembic = project_root / ".venv" / "Scripts" / "alembic.exe"
    else:  # macOS/Linux
        venv_alembic = project_root / ".venv" / "bin" / "alembic"

    # Fallback to system alembic if venv one doesn't exist
    alembic_cmd = str(venv_alembic) if venv_alembic.exists() else "alembic"

    try:
        result = subprocess.run(
            [alembic_cmd, "upgrade", "head"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        print("✅ Migrations completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running migrations: {e}")
        print(e.stdout)
        print(e.stderr)
        return False


def check_status():
    """Check current migration status."""
    print("\n📊 Checking migration status...")
    if os.name == "nt":  # Windows
        venv_alembic = project_root / ".venv" / "Scripts" / "alembic.exe"
    else:  # macOS/Linux
        venv_alembic = project_root / ".venv" / "bin" / "alembic"

    # Fallback to system alembic if venv one doesn't exist
    alembic_cmd = str(venv_alembic) if venv_alembic.exists() else "alembic"

    try:
        result = subprocess.run(
            [alembic_cmd, "current"], cwd=project_root, capture_output=True, text=True, check=True
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error checking status: {e}")
        print(e.stdout)
        print(e.stderr)
        return False


async def setup_store():
    """Initialize LangGraph store tables."""
    print("\n🏪 Setting up LangGraph Store...")
    try:
        from src.flow.store.rext_store import generate_store

        # generate_store() is an async context manager that calls store.setup()
        async with generate_store() as store:
            await store.setup()

        print("✅ Store setup completed successfully")
        return True
    except Exception as e:
        print(f"❌ Error setting up store: {e}")
        # import traceback
        # traceback.print_exc()
        return False


async def seed_database():
    """Reset database, run all migrations, and seed default data & credits."""
    print("🌱 Seeding database (reset + migrate + data seeds)...\n")

    # Reset
    if not await reset_database():
        sys.exit(1)

    # Migrate
    if not run_migrations():
        sys.exit(1)

    # Run all seed scripts (permissions, email templates, subscription plans & credits)
    print("\n🌱 Running data seed scripts...")
    from scripts.seeds.run_all import run_all_seeds
    await run_all_seeds()

    # Seed test users & workspace credits
    print("\n👥 Seeding test users, workspace, and credits...")
    from scripts.seed_test_users import seed_test_users
    await seed_test_users()

    print("\n✅ Database seeded successfully with subscription plan credits!")
    print("   Super admin credentials:")
    print(f"   Email: {os.getenv('SUPER_ADMIN_EMAIL', 'admin@rext.com')}")
    print(f"   Password: {os.getenv('SUPER_ADMIN_PASSWORD', '[see .env]')}")


def print_usage():
    """Print usage information."""
    print(__doc__)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "reset":
        success = asyncio.run(reset_database())
        sys.exit(0 if success else 1)

    elif command == "migrate":
        success = run_migrations()
        if success:
            success = asyncio.run(setup_store())
        sys.exit(0 if success else 1)

    elif command == "seed":
        asyncio.run(seed_database())
        sys.exit(0)

    elif command == "status":
        success = check_status()
        sys.exit(0 if success else 1)

    elif command == "store":
        success = asyncio.run(setup_store())
        sys.exit(0 if success else 1)

    else:
        print(f"❌ Unknown command: {command}\n")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
