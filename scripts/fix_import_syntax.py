#!/usr/bin/env python3
"""
Fix import syntax errors where get_settings import is inside another import block.

This script finds and fixes patterns like:
    from x import (
    from src.api.config import get_settings
        foo,
        bar,
    )

And converts them to:
    from src.api.config import get_settings
    from x import (
        foo,
        bar,
    )
"""

import re
from pathlib import Path


def fix_file(filepath: Path) -> bool:
    """Fix import syntax in a single file. Returns True if changes were made."""
    try:
        content = filepath.read_text()
        original_content = content

        # Pattern: from X import (\nfrom src.api.config import get_settings\n
        # Replace with: from src.api.config import get_settings\nfrom X import (\n
        pattern = r"(from [^\n]+ import \()\n(from src\.api\.config import get_settings)\n"
        replacement = r"\2\n\1\n"

        content = re.sub(pattern, replacement, content)

        if content != original_content:
            filepath.write_text(content)
            print(f"Fixed: {filepath}")
            return True
        return False

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Find and fix all Python files in src/ directory."""
    src_dir = Path("src")
    fixed_count = 0

    for py_file in src_dir.rglob("*.py"):
        if fix_file(py_file):
            fixed_count += 1

    print(f"\nFixed {fixed_count} files")


if __name__ == "__main__":
    main()
