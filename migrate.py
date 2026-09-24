#!/usr/bin/env python3
"""
Alembic Migration Utility Script for Rext Backend

Usage:
    python migrate.py status          - Show current migration status
    python migrate.py upgrade         - Upgrade to latest migration
    python migrate.py downgrade       - Downgrade one migration
    python migrate.py create "message"- Create a new migration
    python migrate.py history         - Show migration history
"""

import os
import sys

from alembic.config import Config

from alembic import command


def get_alembic_config():
    """Get Alembic configuration."""
    alembic_ini_path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    return Config(alembic_ini_path)


def status():
    """Show current migration status."""
    alembic_cfg = get_alembic_config()
    command.current(alembic_cfg, verbose=True)


def upgrade():
    """Upgrade to latest migration."""
    alembic_cfg = get_alembic_config()
    command.upgrade(alembic_cfg, "head")
    print("✅ Database upgraded to latest migration")


def downgrade():
    """Downgrade one migration."""
    alembic_cfg = get_alembic_config()
    response = input("⚠️  Are you sure you want to downgrade? (yes/no): ")
    if response.lower() == "yes":
        command.downgrade(alembic_cfg, "-1")
        print("✅ Database downgraded one migration")
    else:
        print("❌ Downgrade cancelled")


def create_migration(message):
    """Create a new migration."""
    alembic_cfg = get_alembic_config()
    command.revision(alembic_cfg, autogenerate=True, message=message)
    print(f"✅ Migration created: {message}")


def history():
    """Show migration history."""
    alembic_cfg = get_alembic_config()
    command.history(alembic_cfg, verbose=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        status()
    elif cmd == "upgrade":
        upgrade()
    elif cmd == "downgrade":
        downgrade()
    elif cmd == "create":
        if len(sys.argv) < 3:
            print("Error: Migration message required")
            print('Usage: python migrate.py create "your message"')
            sys.exit(1)
        create_migration(sys.argv[2])
    elif cmd == "history":
        history()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
