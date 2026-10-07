#!/usr/bin/env python3
"""
Uploads the official Rext AI logo (emails/assets/rext-logo.png) to MinIO so
transactional emails can reference it via emails.components.header.LOGO_OBJECT_NAME.

The server publishes it at every start (emails.components.header.publish_logo); this
script does the same by hand, for an environment whose server hasn't restarted.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from emails.components.header import LOGO_OBJECT_NAME, publish_logo
from src.utils.storage import storage_service


def main():
    if not storage_service.available:
        print(f"MinIO is not available: {storage_service.last_error}")
        sys.exit(1)

    if not publish_logo():
        print("Failed to upload logo to MinIO")
        sys.exit(1)

    print(f"Uploaded logo to MinIO: {LOGO_OBJECT_NAME}")
    print(f"Public URL: {storage_service.get_file_url(LOGO_OBJECT_NAME)}")


if __name__ == "__main__":
    main()
