"""
Storage Configuration

Configuration for file storage backends (Cloudflare R2, Local).
"""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


StorageBackendType = Literal["r2", "local"]


class StorageSettings(BaseSettings):
    """Storage configuration settings"""

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
    
    # Presigned URL configuration
    presigned_url_expiration: int = 3600  # Default 1 hour (in seconds)
    presigned_url_max_expiration: int = 604800  # Maximum 7 days (R2 limit, in seconds)
    thumbnail_url_expiration: int = 86400  # Default 24 hours for thumbnails (in seconds)

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

    from typing import Dict, List, Literal, Optional
    from pydantic_settings import BaseSettings, SettingsConfigDict


    StorageBackendType = Literal["r2", "local"]


    # Centralized MIME type registry — single source of truth
    MIME_TYPE_REGISTRY: Dict[str, Dict[str, any]] = {
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
        r2_bucket: str = ""
        r2_account_id: str = ""
        r2_access_key_id: str = ""
        r2_secret_access_key: str = ""
        r2_public_domain: str = ""

        # Local storage configuration
        local_storage_path: str = "./media"
        local_storage_url_base: str = "/media"

        # File upload limits (in bytes)
        max_file_size: int = 20 * 1024 * 1024  # 20MB default
        max_image_size: int = 10 * 1024 * 1024  # 10MB for images
        max_video_size: int = 100 * 1024 * 1024  # 100MB for videos

        # Derived allowed type lists from the registry
        @property
        def allowed_image_types(self) -> List[str]:
            return get_allowed_types_by_category("image")

        @property
        def allowed_document_types(self) -> List[str]:
            return get_allowed_types_by_category("document")

        @property
        def allowed_video_types(self) -> List[str]:
            return get_allowed_types_by_category("video")

        # Image processing
        thumbnail_size: int = 300
        max_image_width: int = 2000
        max_image_height: int = 2000
        image_quality: int = 85

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=True,
            extra="ignore",
        )


    storage_settings = StorageSettings()
