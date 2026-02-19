
"""
Storage Configuration

Configuration for file storage backends (Cloudflare R2, Local).
"""

from typing import Literal, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


StorageBackendType = Literal["r2", "local"]


class StorageSettings(BaseSettings):
    """Storage configuration settings"""

    # Backend selection
    storage_backend: StorageBackendType = "local"

    # Cloudflare R2 configuration
    r2_bucket: str = ""
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_public_domain: str = ""  # Optional: Custom domain for public files

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @model_validator(mode='after')
    def validate_r2_credentials(self) -> 'StorageSettings':
        """Validate that all required R2 credentials are provided when R2 backend is selected."""
        if self.storage_backend == "r2":
            required_fields = {
                "r2_bucket": self.r2_bucket,
                "r2_account_id": self.r2_account_id,
                "r2_access_key_id": self.r2_access_key_id,
                "r2_secret_access_key": self.r2_secret_access_key,
            }
            missing = [name for name, value in required_fields.items() if not value.strip()]
            if missing:
                raise ValueError(
                    f"Storage backend is set to 'r2' but the following required "
                    f"credentials are missing or empty: {', '.join(missing)}. "
                    f"Set these via environment variables or .env file."
                )
        return self


# Global settings instance
storage_settings = StorageSettings()