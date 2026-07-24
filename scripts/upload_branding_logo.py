#!/usr/bin/env python3
"""
Uploads the official Rext AI logo (emails/assets/rext-logo.png) to MinIO so
transactional emails can reference it via emails.components.header.LOGO_OBJECT_NAME.

Run once per environment (dev, staging, prod) whenever the logo asset changes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from emails.components.header import LOGO_OBJECT_NAME
from src.utils.storage import storage_service

LOGO_FILE = Path(__file__).parent.parent / "emails" / "assets" / "rext-logo.png"


def main():
    if not storage_service.available:
        print(f"MinIO is not available: {storage_service.last_error}")
        sys.exit(1)

    file_data = LOGO_FILE.read_bytes()
    uploaded_url = storage_service.upload_file(
        file_data=file_data,
        object_name=LOGO_OBJECT_NAME,
        content_type="image/png"
    )

    if not uploaded_url:
        print("Failed to upload logo to MinIO")
        sys.exit(1)

    print(f"Uploaded logo to MinIO: {LOGO_OBJECT_NAME}")
    print(f"Public URL: {storage_service.get_file_url(LOGO_OBJECT_NAME)}")


if __name__ == "__main__":
    main()
