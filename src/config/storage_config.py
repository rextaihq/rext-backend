"""
Storage Configuration

Configuration for file storage backends (Cloudflare R2, Local).
"""

from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator


StorageBackendType = Literal["r2", "local"]


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
    local_storage_path: str = "./media"
    local_storage_url_base: str = "/media"

    # File upload limits (in bytes)
    max_file_size: int = 20 * 1024 * 1024  # 20MB default
    max_image_size: int = 10 * 1024 * 1024  # 10MB for images
    max_video_size: int = 100 * 1024 * 1024  # 100MB for videos

    # Allowed file types
    allowed_image_types: list = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml"
    ]

    allowed_document_types: list = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown"
    ]

    allowed_video_types: list = [
        "video/mp4",
        "video/webm",
        "video/quicktime"
    ]

    # Image processing
    thumbnail_size: int = 300  # Max dimension for thumbnails
    max_image_width: int = 2000  # Max width for optimized images
    max_image_height: int = 2000  # Max height for optimized images
    image_quality: int = 85  # JPEG quality (1-100)

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
