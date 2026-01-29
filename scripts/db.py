#!/usr/bin/env python3
"""
Database management script for rext-backend

Usage:
    python scripts/db.py reset    - Reset database (drops all data)
    python scripts/db.py migrate  - Run all migrations
    python scripts/db.py seed     - Reset + migrate (fresh start)
    python scripts/db.py status   - Check migration status
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
env_path = project_root / ".env"
load_dotenv(env_path)


async def reset_database():
    """Reset the database by dropping and recreating the public schema."""
    db_url = os.getenv("POSTGRES_URI_CUSTOM")
    if not db_url:
        print("❌ Error: POSTGRES_URI_CUSTOM not set in .env")
        sys.exit(1)

    # Convert to asyncpg URL
    if not db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    print("⚠️  WARNING: This will delete ALL data in the database!")
    print(f"Database: {db_url.split('@')[-1]}")  # Show only host/db part

    try:
        engine = create_async_engine(db_url)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
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
            check=True
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
            [alembic_cmd, "current"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True
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


async def seed_database():
    """Reset database and run all migrations (fresh start)."""
    print("🌱 Seeding database (reset + migrate)...\n")

    # Reset
    if not await reset_database():
        sys.exit(1)

    # Migrate
    if not run_migrations():
        sys.exit(1)

    print("\n✅ Database seeded successfully!")
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
        sys.exit(0 if success else 1)

    elif command == "seed":
        asyncio.run(seed_database())
        sys.exit(0)

    elif command == "status":
        success = check_status()
        sys.exit(0 if success else 1)

    else:
        print(f"❌ Unknown command: {command}\n")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
