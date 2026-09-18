#!/usr/bin/env python3
"""Script to replace print() statements with logger calls."""

import re
from pathlib import Path
import subprocess


def has_logger_import(content: str) -> bool:
    """Check if file already has logger import."""
    return (
        "from src.api.lib.logger import auto_logger" in content
        or "from src.utils.logger import logger" in content
    )


def add_logger_import(content: str) -> str:
    """Add logger import to file after existing imports."""
    # Find the last import statement
    import_pattern = r"((?:^(?:from|import)\s+.*$\n)+)"
    matches = list(re.finditer(import_pattern, content, re.MULTILINE))

    if matches:
        # Insert after the last import block
        last_match = matches[-1]
        insert_pos = last_match.end()

        # Add logger import and initialization
        new_imports = "\nfrom src.api.lib.logger import auto_logger\n\nlogger = auto_logger()\n"
        content = content[:insert_pos] + new_imports + content[insert_pos:]
    else:
        # No imports found, add at the beginning
        content = (
            "from src.api.lib.logger import auto_logger\n\nlogger = auto_logger()\n\n" + content
        )

    return content


def replace_print_statements(content: str) -> str:
    """Replace print() statements with logger calls."""
    lines = content.split("\n")
    modified_lines = []

    for line in lines:
        # Skip if it's a comment
        stripped = line.strip()
        if stripped.startswith("#"):
            modified_lines.append(line)
            continue

        # Simple print() replacement patterns
        # print("message") -> logger.info("message")
        # print(f"...") -> logger.info(f"...")
        # print(variable) -> logger.info(str(variable))

        if "print(" in line:
            # Replace print( with logger.info(
            modified_line = re.sub(r"\bprint\s*\(", "logger.info(", line)
            modified_lines.append(modified_line)
        else:
            modified_lines.append(line)

    return "\n".join(modified_lines)


def process_file(file_path: Path) -> bool:
    """Process a single file to replace print statements."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Skip if no print statements
        if "print(" not in content:
            return False

        # Add logger import if needed
        if not has_logger_import(content):
            content = add_logger_import(content)

        # Replace print statements
        content = replace_print_statements(content)

        # Write back
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"✅ Updated: {file_path}")
        return True
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")
        return False


def main():
    """Main function to process all Python files."""
    # Get list of files with print statements
    result = subprocess.run(
        ["grep", "-r", "print(", "src/", "--include=*.py"], capture_output=True, text=True
    )

    if result.returncode != 0:
        print("No files with print() statements found.")
        return

    # Extract unique file paths
    files = set()
    for line in result.stdout.split("\n"):
        if line:
            file_path = line.split(":")[0]
            files.add(Path(file_path))

    print(f"Found {len(files)} files with print() statements")
    print("=" * 60)

    # Process each file
    updated_count = 0
    for file_path in sorted(files):
        if process_file(file_path):
            updated_count += 1

    print("=" * 60)
    print(f"\n✅ Successfully updated {updated_count} files")
    print(f"📋 Total files processed: {len(files)}")


if __name__ == "__main__":
    main()
