
"""
Storage Configuration

Configuration for file storage backends (Cloudflare R2, Local).
"""

from typing import Dict, List, Literal, Optional, Any
from pydantic import model_validator, field_validator
from pathlib import Path
from typing import Literal
from pydantic import field_validator
from typing import Literal, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


StorageBackendType = Literal["r2", "local"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Centralized MIME type registry — single source of truth
MIME_TYPE_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Images
    "image/jpeg": {"extensions": [".jpg", ".jpeg"], "category": "image"},
    "image/png": {"extensions": [".png"], "category": "image"},
    "image/gif": {"extensions": [".gif"], "category": "image"},
    "image/webp": {"extensions": [".webp"], "category": "image"},
    "image/svg+xml": {"extensions": [".svg"], "category": "image"},

    # Documents
    "application/pdf": {"extensions": [".pdf"], "category": "document"},
    "application/msword": {"extensions": [".doc"], "category": "document"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "extensions": [".docx"], "category": "document"
    },
    "text/plain": {"extensions": [".txt", ".md"], "category": "document"},
    "text/markdown": {"extensions": [".md"], "category": "document"},

    # Videos
    "video/mp4": {"extensions": [".mp4"], "category": "video"},
    "video/webm": {"extensions": [".webm"], "category": "video"},
    "video/quicktime": {"extensions": [".mov"], "category": "video"},
}

# Build reverse lookup: extension -> MIME type
EXTENSION_TO_MIME: Dict[str, str] = {}
for mime, info in MIME_TYPE_REGISTRY.items():
    for ext in info["extensions"]:
        EXTENSION_TO_MIME[ext.lstrip(".")] = mime


def get_allowed_types_by_category(category: str) -> List[str]:
    """Get all allowed MIME types for a given category."""
    return [mime for mime, info in MIME_TYPE_REGISTRY.items() if info["category"] == category]


def get_all_allowed_types() -> List[str]:
    """Get all allowed MIME types across all categories."""
    return list(MIME_TYPE_REGISTRY.keys())


def get_mime_from_extension(ext: str) -> Optional[str]:
    """
    Get MIME type from file extension using the centralized registry.

    Args:
        ext: File extension with or without dot (e.g., '.jpg' or 'jpg')

    Returns:
        MIME type string or None if extension is not in the registry
    """
    ext = ext.lstrip(".")
    return EXTENSION_TO_MIME.get(ext)


class StorageSettings(BaseSettings):
    """Storage configuration settings"""

    # Backend selection
    storage_backend: StorageBackendType = "local"

    # Cloudflare R2 configuration
    r2_bucket: Optional[str] = None
    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_public_domain: Optional[str] = None  # Optional: Custom domain for public files

    # Local storage configuration
    local_storage_path: Path = PROJECT_ROOT / "media"
    local_storage_url_base: str = "/media"

    @field_validator("local_storage_path", mode="before")
    @classmethod
    def normalize_local_storage_path(cls, value: str | Path) -> Path:
        path = Path(value).expanduser() if value else (PROJECT_ROOT / "media")
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        return path

    # File upload limits (in bytes)
    max_file_size: int = 20 * 1024 * 1024  # 20MB default
    max_image_size: int = 10 * 1024 * 1024  # 10MB for images
    max_video_size: int = 100 * 1024 * 1024  # 100MB for videos
    
    # Presigned URL configuration
    presigned_url_expiration: int = 3600  # Default 1 hour (in seconds)
    presigned_url_max_expiration: int = 604800  # Maximum 7 days (R2 limit, in seconds)
    thumbnail_url_expiration: int = 86400  # Default 24 hours for thumbnails (in seconds)

    # Derived allowed type lists from the registry
    @property
    def allowed_image_types(self) -> List[str]:
        return get_allowed_types_by_category("image")

    @property
    def allowed_document_types(self) -> List[str]:
        return get_allowed_types_by_category("document")

    @field_validator(
        "r2_bucket",
        "r2_account_id",
        "r2_access_key_id",
        "r2_secret_access_key",
        mode="before"
    )
    @classmethod
    def normalize_blank_credentials(cls, v: Optional[str]) -> Optional[str]:
        """Normalize blank strings to None"""
        if v is None:
            return None
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v

    @model_validator(mode="after")
    def validate_required_storage_credentials(self) -> "StorageSettings":
        """Fail fast if any required R2 credential is missing when R2 backend is selected"""
        if self.storage_backend == "r2":
            missing = []
            if not self.r2_bucket:
                missing.append("R2_BUCKET")
            if not self.r2_account_id:
                missing.append("R2_ACCOUNT_ID")
            if not self.r2_access_key_id:
                missing.append("R2_ACCESS_KEY_ID")
            if not self.r2_secret_access_key:
                missing.append("R2_SECRET_ACCESS_KEY")
            if missing:
                raise ValueError(
                    "Missing required R2 storage credentials: " + ", ".join(missing)
                )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Global settings instance
storage_settings = StorageSettings()
