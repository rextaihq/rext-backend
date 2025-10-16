#!/usr/bin/env python3
"""
Script to migrate os.getenv("FRONTEND_URL") to settings.FRONTEND_URL
"""
import re
from pathlib import Path

FILES_TO_UPDATE = [
    "src/api/routes/workspaces/workspace_invitations.py",
    "src/api/routes/workspaces/workspace_members.py",
    "src/api/routes/workspaces/invitations.py/modules/invitation_manage.py",
    "src/api/routes/workspaces/invitations.py/modules/invitation_create.py",
    "src/api/routes/users/auth.py",
    "src/api/routes/users/management.py",
    "src/api/routes/users/password.py",
    "src/api/routes/email/preview.py",
    "src/services/knowledge_service.py",
    "src/services/langgraph_content_service.py",
]

def migrate_file(file_path: Path):
    """Migrate a single file."""
    print(f"Processing: {file_path}")

    with open(file_path, "r") as f:
        content = f.read()

    original_content = content

    # Replace os.getenv("FRONTEND_URL", "...") with settings.FRONTEND_URL
    content = re.sub(
        r'os\.getenv\("FRONTEND_URL",\s*"[^"]+"\)',
        'settings.FRONTEND_URL',
        content
    )

    # Replace os.getenv("FRONTEND_URL") with settings.FRONTEND_URL
    content = re.sub(
        r'os\.getenv\("FRONTEND_URL"\)',
        'settings.FRONTEND_URL',
        content
    )

    # Add import if needed and not already present
    if "settings.FRONTEND_URL" in content and "from src.api.config import" not in content:
        # Find where to insert import (after other imports)
        import_match = re.search(r'(from src\.[^\n]+\n)+', content)
        if import_match:
            insert_pos = import_match.end()
            content = content[:insert_pos] + "from src.api.config import get_settings\n" + content[insert_pos:]

            # Add settings instantiation after imports
            # Find first function or class definition
            func_match = re.search(r'\n(async )?def |class ', content[insert_pos:])
            if func_match:
                func_pos = insert_pos + func_match.start()
                content = content[:func_pos] + "\n# Get settings instance\nsettings = get_settings()\n" + content[func_pos:]

    if content != original_content:
        with open(file_path, "w") as f:
            f.write(content)
        print(f"  ✓ Updated {file_path}")
        return True
    else:
        print(f"  - No changes needed for {file_path}")
        return False

def main():
    """Main migration function."""
    base_path = Path(__file__).parent.parent
    updated_count = 0

    for file_rel_path in FILES_TO_UPDATE:
        file_path = base_path / file_rel_path
        if file_path.exists():
            if migrate_file(file_path):
                updated_count += 1
        else:
            print(f"  ⚠ File not found: {file_path}")

    print(f"\n✅ Migration complete! Updated {updated_count} files.")

if __name__ == "__main__":
    main()
