#!/usr/bin/env python3
"""Validate that new migration revision IDs follow Alembic conventions."""

import re
import sys
from pathlib import Path

# Known historical non-standard IDs (do not flag these)
KNOWN_EXCEPTIONS = {
    "seed005",
    "seed006",
    "seed007",
    "seed008",
    "seed009",
    "admin001",
    "inv001",
    "inv002",
    "ls20251020",
    "onb20251020",
    "rem20251020",
    "pgv001",
    "pgv002",
    "pgv003",
    "20251111_bio_notif",
    "b2c3d4e5f6g7",
    "c3d4e5f6g7h8",
    "d1e2f3g4h5i6",
    "g1h2i3j4k5l6",
    "h2i3j4k5l6m7",
    # Additional ones found in codebase
    "a1b2c3d4e5f6",
    "a1f2e3d4c5b6",
    "a8b9c0d1e2f3",
    "f23456789abc",
    "f9e8d7c6b5a4",
}

# Standard Alembic hex ID pattern (12 lowercase hex chars)
HEX_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def main():
    # Use absolute path or relative to project root
    project_root = Path(__file__).parent.parent
    versions_dir = project_root / "alembic/versions"

    if not versions_dir.exists():
        print(f"Error: Versions directory not found at {versions_dir}")
        sys.exit(1)

    errors = []

    for migration_file in versions_dir.glob("*.py"):
        if migration_file.name == "__pycache__":
            continue

        content = migration_file.read_text(encoding="utf-8")
        # Regex to find revision = '...' or revision: str = '...'
        match = re.search(r"revision[:\s\w]*=\s*['\"]([^'\"]+)['\"]", content)
        if match:
            revision_id = match.group(1)
            if revision_id in KNOWN_EXCEPTIONS:
                continue
            if not HEX_PATTERN.match(revision_id):
                errors.append(f"{migration_file.name}: non-standard revision ID '{revision_id}'")

    if errors:
        print("Migration ID validation failed:")
        for error in errors:
            print(f"  - {error}")
        print("\nNew migrations must use standard 12-character lowercase hex IDs.")
        print("Refer to alembic/MIGRATION_CONVENTIONS.md for details.")
        sys.exit(1)

    print("All migration IDs are valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
