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

import os
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from uuid import uuid4

import filetype
from fastapi import UploadFile
from werkzeug.utils import secure_filename
from PIL import Image

from src.utils.logger import logger
from src.api.middleware.exceptions import RextValidationException
from src.api.config import get_settings

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

# Allowed MIME types (magic number)
ALLOWED_MIME_TYPES = {
    # Documents
    "application/pdf": {"extensions": [".pdf"], "category": "document"},
    "text/plain": {"extensions": [".txt", ".md"], "category": "document"},
    "application/msword": {"extensions": [".doc"], "category": "document"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "extensions": [".docx"],
        "category": "document"
    },
    "application/rtf": {"extensions": [".rtf"], "category": "document"},

    # Spreadsheets
    "application/vnd.ms-excel": {"extensions": [".xls"], "category": "spreadsheet"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
        "extensions": [".xlsx"],
        "category": "spreadsheet"
    },
    "text/csv": {"extensions": [".csv"], "category": "spreadsheet"},

    # Images
    "image/png": {"extensions": [".png"], "category": "image"},
    "image/jpeg": {"extensions": [".jpg", ".jpeg"], "category": "image"},
    "image/gif": {"extensions": [".gif"], "category": "image"},
    "image/webp": {"extensions": [".webp"], "category": "image"},
}

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
    enable_virus_scan: bool = False
) -> Dict:
    """
    Validate and securely store uploaded file.

    Args:
        file: FastAPI UploadFile object
        workspace_id: Workspace UUID for scoping
        allowed_types: List of allowed MIME types (None = use defaults)
        max_size_mb: Max file size in MB (None = use default)
        enable_virus_scan: Whether to scan for viruses (requires ClamAV)

    Returns:
        Dict with file metadata:
        {
            "safe_filename": "sanitized_name.pdf",
            "unique_filename": "20251006_143022_a1b2c3d4e5f6.pdf",
            "secure_path": "/secure_uploads/workspace_xxx/xxx.pdf",
            "mime_type": "application/pdf",
            "size": 12345,
            "hash": "sha256_hash",
            "original_filename": "user_upload.pdf"
        }

    Raises:
        RextValidationException: If validation fails
    """
    allowed_types = allowed_types or list(ALLOWED_MIME_TYPES.keys())
    max_size_bytes = (max_size_mb or MAX_FILE_SIZE_MB) * 1024 * 1024

    # Step 1: Validate filename
    if not file.filename:
        raise RextValidationException("Filename is required")

    safe_filename = _sanitize_filename(file.filename)

    # Step 2: Check file extension (preliminary check)
    file_ext = Path(safe_filename).suffix.lower()
    if file_ext in DANGEROUS_EXTENSIONS:
        raise RextValidationException(
            f"File type '{file_ext}' is not allowed for security reasons",
            field_errors={"file": [f"Extension {file_ext} is forbidden"]}
        )

    # Step 3: Create workspace upload directory
    upload_base_dir = get_upload_base_dir()
    workspace_dir = upload_base_dir / f"workspace_{workspace_id}"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Step 4: Generate unique filename (prevent collisions)
    unique_id = uuid4().hex[:12]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_filename = f"{timestamp}_{unique_id}{file_ext}"
    file_path = workspace_dir / unique_filename

    # Step 5: Stream file to disk and validate
    try:
        file_size = 0
        file_hash = hashlib.sha256()
        mime_buffer = b""

        with open(file_path, "wb") as f:
            # Read file in chunks (memory efficient)
            while chunk := await file.read(CHUNK_SIZE):
                file_size += len(chunk)

                # Check size limit
                if file_size > max_size_bytes:
                    f.close()
                    file_path.unlink()  # Delete partial file
                    raise RextValidationException(
                        f"File size exceeds maximum allowed size of {max_size_mb or MAX_FILE_SIZE_MB}MB",
                        field_errors={"file": [f"Maximum size: {max_size_mb or MAX_FILE_SIZE_MB}MB"]}
                    )

                # Collect bytes for magic number detection
                if len(mime_buffer) < 2048:
                    mime_buffer += chunk

                # Calculate hash
                file_hash.update(chunk)

                # Write to disk
                f.write(chunk)

        # Step 6: Validate MIME type (magic number)
        detected_type = filetype.guess(mime_buffer)

        if detected_type is None:
            # Fallback to text/plain for text files (including CSV)
            try:
                mime_buffer.decode('utf-8')
                detected_mime = "text/plain"
                # Check if it's a CSV by extension
                if file_ext == ".csv" and "text/csv" in allowed_types:
                    detected_mime = "text/csv"
            except UnicodeDecodeError:
                file_path.unlink()  # Delete invalid file
                raise RextValidationException(
                    "Unable to determine file type",
                    field_errors={"file": ["Invalid or unknown file type"]}
                )
        else:
            detected_mime = detected_type.mime

        # Special handling for text/csv (detected as text/plain)
        if detected_mime == "text/plain" and file_ext == ".csv" and "text/csv" in allowed_types:
            detected_mime = "text/csv"

        if detected_mime not in allowed_types:
            file_path.unlink()  # Delete invalid file
            raise RextValidationException(
                f"File type '{detected_mime}' is not allowed. Allowed types: {', '.join(allowed_types)}",
                field_errors={"file": [f"Invalid file type: {detected_mime}"]}
            )

        # Step 7: Image dimension validation (for images)
        image_metadata = {}
        if detected_mime.startswith("image/"):
            image_metadata = _validate_image_dimensions(file_path)

        # Step 8: Virus scan (optional) - placeholder for future
        if enable_virus_scan:
            logger.warning("Virus scanning requested but not implemented (ClamAV not configured)")

        # Step 9: Return metadata
        logger.info(
            f"File uploaded successfully: {safe_filename} ({detected_mime}, {file_size} bytes)",
            extra={
                "workspace_id": workspace_id,
                "mime_type": detected_mime,
                "file_size": file_size
            }
        )

        return {
            "safe_filename": safe_filename,
            "unique_filename": unique_filename,
            "secure_path": str(file_path),
            "mime_type": detected_mime,
            "size": file_size,
            "hash": file_hash.hexdigest(),
            "original_filename": file.filename,
            **image_metadata  # Include image dimensions if it's an image
        }

    except RextValidationException:
        # Re-raise validation exceptions
        raise

    except Exception as e:
        # Cleanup on unexpected error
        if file_path.exists():
            file_path.unlink()

        logger.exception(f"Error storing file: {e}")
        raise RextValidationException(
            "Failed to process file upload",
            context={"error": str(e)}
        )


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal and other attacks.

    - Remove path separators
    - Remove null bytes
    - Limit length
    - Use werkzeug's secure_filename

    Args:
        filename: Original filename from user

    Returns:
        Sanitized filename safe for storage
    """
    # Remove null bytes
    filename = filename.replace("\x00", "")

    # Remove path separators and traversal attempts
    filename = filename.replace("/", "_").replace("\\", "_").replace("..", "_")

    # Use werkzeug's secure_filename (removes special chars)
    filename = secure_filename(filename)

    # Limit length (filesystem limits)
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext

    # Ensure not empty
    if not filename or filename == "_":
        filename = f"upload_{uuid4().hex[:8]}"

    return filename


def _validate_image_dimensions(file_path: Path) -> Dict:
    """
    Validate image dimensions and extract metadata.

    Args:
        file_path: Path to image file

    Returns:
        Dict with image metadata (width, height, format)

    Raises:
        RextValidationException: If image dimensions are invalid
    """
    try:
        with Image.open(file_path) as img:
            width, height = img.size

            # Check minimum dimensions
            if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
                file_path.unlink()  # Delete invalid image
                raise RextValidationException(
                    f"Image dimensions too small. Minimum: {MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT}px",
                    field_errors={"file": [f"Image must be at least {MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT}px"]}
                )

            # Check maximum dimensions
            if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
                file_path.unlink()  # Delete oversized image
                raise RextValidationException(
                    f"Image dimensions too large. Maximum: {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}px",
                    field_errors={"file": [f"Image must not exceed {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}px"]}
                )

            logger.info(f"Image validated: {width}x{height}px, format: {img.format}")

            return {
                "image_width": width,
                "image_height": height,
                "image_format": img.format,
                "image_mode": img.mode
            }

    except RextValidationException:
        raise
    except Exception as e:
        logger.error(f"Error validating image: {e}")
        file_path.unlink()  # Delete corrupted image
        raise RextValidationException(
            "Invalid or corrupted image file",
            field_errors={"file": ["Unable to process image"]}
        )


async def delete_file(file_path: str) -> bool:
    """
    Securely delete file from storage.

    Args:
        file_path: Path to file to delete

    Returns:
        True if deleted, False if file not found
    """
    try:
        path = Path(file_path)
        upload_base_dir = get_upload_base_dir()

        # Validate path is within upload directory (prevent deletion of arbitrary files)
        try:
            path.resolve().relative_to(upload_base_dir.resolve())
        except ValueError:
            logger.warning(f"Attempt to delete file outside upload directory: {file_path}")
            return False

        if path.exists() and path.is_file():
            path.unlink()
            logger.info(f"File deleted: {file_path}")
            return True

        return False

    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        return False


def get_file_info(file_path: str) -> Optional[Dict]:
    """
    Get metadata about stored file.

    Args:
        file_path: Path to file

    Returns:
        Dict with file metadata or None if file doesn't exist
    """
    try:
        path = Path(file_path)

        if not path.exists():
            return None

        stat = path.stat()

        return {
            "path": str(path),
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "exists": True
        }
    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {e}")
        return None
