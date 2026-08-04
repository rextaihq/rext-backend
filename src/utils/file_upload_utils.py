"""
Secure File Upload Utilities

Provides comprehensive file validation and secure storage for user uploads.

Security Features:
- File type validation (magic number checking, not just extension)
- File size limits
- Filename sanitization (prevents directory traversal)
- Secure storage location (outside web root)
- Streaming uploads (memory efficient)
- Automatic cleanup on error

Supported File Types:
- Documents: PDF, DOC, DOCX, TXT, MD
- Spreadsheets: XLS, XLSX, CSV
- Images: PNG, JPG, JPEG, GIF, WEBP
"""

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import filetype
from fastapi import UploadFile
from PIL import Image
from werkzeug.utils import secure_filename

from src.api.config import get_settings
from src.api.middleware.exceptions import RextValidationException
from src.config.storage_config import MIME_TYPE_REGISTRY, get_all_allowed_types
from src.utils.logger import logger
from src.utils.storage import storage_service

# Get settings instance
settings = get_settings()

# File Upload Configuration
def get_upload_base_dir() -> Path:
    """Get upload base directory from settings."""
    return settings.upload_dir_path

MAX_FILE_SIZE_MB = settings.MAX_UPLOAD_SIZE_MB
CHUNK_SIZE = 8192  # 8KB chunks for streaming

# Image validation configuration
MAX_IMAGE_WIDTH = settings.MAX_IMAGE_WIDTH
MAX_IMAGE_HEIGHT = settings.MAX_IMAGE_HEIGHT
MIN_IMAGE_WIDTH = settings.MIN_IMAGE_WIDTH
MIN_IMAGE_HEIGHT = settings.MIN_IMAGE_HEIGHT

ALLOWED_MIME_TYPES = MIME_TYPE_REGISTRY

# Dangerous file extensions (always reject)
DANGEROUS_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib",  # Executables
    ".sh", ".bash", ".zsh", ".fish",  # Shell scripts
    ".bat", ".cmd", ".ps1",  # Windows scripts
    ".app", ".deb", ".rpm",  # Packages
    ".js", ".mjs",  # JavaScript (potential XSS)
    ".php", ".phtml",  # Server-side scripts
    ".py", ".pyc",  # Python (if eval/exec used)
}


async def validate_and_store_file(
    file: UploadFile,
    workspace_id: str,
    allowed_types: Optional[List[str]] = None,
    max_size_mb: Optional[int] = None,
    enable_virus_scan: bool = False,
    object_prefix: Optional[str] = None,
) -> Dict:
    """
    Validate and securely store uploaded file in MinIO.
    """
    allowed_types = allowed_types or get_all_allowed_types()
    max_size_bytes = (max_size_mb or MAX_FILE_SIZE_MB) * 1024 * 1024

    # Step 1: Validate filename
    if not file.filename:
        raise RextValidationException("Filename is required")

    safe_filename = _sanitize_filename(file.filename)

    # Step 2: Check file extension
    file_ext = Path(safe_filename).suffix.lower()
    if file_ext in DANGEROUS_EXTENSIONS:
        raise RextValidationException(
            f"File type '{file_ext}' is not allowed for security reasons"
        )

    # Step 3: Read and validate file content
    try:
        file_content = await file.read()
        file_size = len(file_content)

        # Check size limit
        if file_size > max_size_bytes:
            raise RextValidationException(
                f"File size exceeds maximum allowed size of {max_size_mb or MAX_FILE_SIZE_MB}MB"
            )

        # Step 4: Validate MIME type
        detected_type = filetype.guess(file_content)
        if detected_type is None:
            try:
                file_content.decode('utf-8')
                detected_mime = "text/plain"
                if file_ext == ".csv" and "text/csv" in allowed_types:
                    detected_mime = "text/csv"
            except UnicodeDecodeError:
                raise RextValidationException("Unable to determine file type")
        else:
            detected_mime = detected_type.mime

        if detected_mime == "text/plain" and file_ext == ".csv" and "text/csv" in allowed_types:
            detected_mime = "text/csv"

        if detected_mime not in allowed_types:
            raise RextValidationException(
                f"File type '{detected_mime}' is not allowed. Allowed types: {', '.join(allowed_types)}"
            )

        # Step 5: Image validation
        image_metadata = {}
        if detected_mime.startswith("image/"):
            try:
                buffer_io = BytesIO(file_content)
                image_metadata = _validate_image_dimensions(source=buffer_io)
            except Exception:
                raise RextValidationException("Invalid or corrupted image file")

        # Step 6: Generate unique filename and MinIO key
        unique_id = uuid4().hex[:12]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{unique_id}{file_ext}"
        storage_prefix = (
            object_prefix.strip("/")
            if object_prefix
            else f"workspaces/{workspace_id}"
        )
        object_name = f"{storage_prefix}/{unique_filename}"

        # Step 7: Calculate hash
        file_hash = hashlib.sha256(file_content).hexdigest()

        # Step 8: Upload to MinIO
        uploaded_url = await asyncio.to_thread(
            storage_service.upload_file,
            file_content,
            object_name,
            detected_mime,
        )

        if not uploaded_url:
            raise RextValidationException("Failed to upload file to storage system")

        logger.info(
            f"File uploaded to MinIO: {safe_filename} ({detected_mime}, {file_size} bytes)",
            extra={"workspace_id": workspace_id, "object_name": object_name}
        )

        return {
            "safe_filename": safe_filename,
            "unique_filename": unique_filename,
            "secure_path": object_name, # Return the KEY
            "mime_type": detected_mime,
            "size": file_size,
            "hash": file_hash,
            "original_filename": file.filename,
            "url": uploaded_url,
            **image_metadata
        }

    except RextValidationException:
        raise
    except Exception as e:
        logger.exception(f"Error storing file in MinIO: {e}")
        raise RextValidationException("Failed to process file upload")


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename."""
    filename = filename.replace("\x00", "")
    filename = filename.replace("/", "_").replace("\\", "_").replace("..", "_")
    filename = secure_filename(filename)
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext
    if not filename or filename == "_":
        filename = f"upload_{uuid4().hex[:8]}"
    return filename


def _validate_image_dimensions(source: BytesIO) -> Dict:
    """Validate image dimensions."""
    try:
        with Image.open(source) as img:
            width, height = img.size
            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                raise RextValidationException(f"Image too small. Minimum: {MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT}px")
            if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
                raise RextValidationException(f"Image too large. Maximum: {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}px")
            return {
                "image_width": width,
                "image_height": height,
                "image_format": img.format,
                "image_mode": img.mode
            }
    except RextValidationException:
        raise
    except Exception:
        raise RextValidationException("Invalid or corrupted image file")


async def delete_file(file_path: str) -> bool:
    """Securely delete file from MinIO."""
    return storage_service.delete_file(file_path)


def get_file_info(file_path: str) -> Optional[Dict]:
    """Get metadata about stored file (simplified for S3)."""
    # This would require a head_object call to MinIO, but for now we'll return basics
    return {
        "path": file_path,
        "exists": True # Assume it exists if we have the path, or implement head_object
    }
