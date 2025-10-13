"""
Storage Service

Provides abstraction layer for file storage with support for:
- Cloudflare R2 (S3-compatible, zero egress fees)
- Local filesystem (for development/self-hosted)

Uses boto3 for R2 communication (S3-compatible API).
"""

import os
import boto3
from typing import BinaryIO, Optional, Tuple
from abc import ABC, abstractmethod
import aiofiles
import hashlib
from datetime import datetime
from botocore.exceptions import ClientError
import asyncio
from functools import partial


class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    async def upload(
        self,
        file: BinaryIO,
        path: str,
        content_type: str,
        metadata: Optional[dict] = None
    ) -> str:
        """
        Upload file and return storage path.

        Args:
            file: File object to upload
            path: Destination path/key
            content_type: MIME type
            metadata: Optional metadata dict

        Returns:
            Storage path/key
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> None:
        """
        Delete file from storage.

        Args:
            path: File path/key to delete
        """
        pass

    @abstractmethod
    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """
        Get URL to access file.

        Args:
            path: File path/key
            expires_in: URL expiration in seconds

        Returns:
            Accessible URL (presigned for private files)
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        Check if file exists.

        Args:
            path: File path/key

        Returns:
            True if file exists
        """
        pass


class CloudflareR2Backend(StorageBackend):
    """
    Cloudflare R2 storage backend.

    R2 is S3-compatible with zero egress fees.
    Uses boto3 with custom endpoint for R2.
    """

    def __init__(
        self,
        bucket: str,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        public_domain: Optional[str] = None
    ):
        """
        Initialize Cloudflare R2 backend.

        Args:
            bucket: R2 bucket name
            account_id: Cloudflare account ID
            access_key_id: R2 access key ID
            secret_access_key: R2 secret access key
            public_domain: Optional public domain for R2 bucket (for public URLs)
        """
        self.bucket = bucket
        self.account_id = account_id
        self.public_domain = public_domain

        # R2 endpoint format: https://<account_id>.r2.cloudflarestorage.com
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"

        # Initialize S3-compatible client for R2
        self.s3 = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name='auto'  # R2 uses 'auto' for region
        )

    async def upload(
        self,
        file: BinaryIO,
        path: str,
        content_type: str,
        metadata: Optional[dict] = None
    ) -> str:
        """Upload file to Cloudflare R2."""
        extra_args = {
            'ContentType': content_type,
            'ACL': 'private'  # Default to private
        }

        if metadata:
            extra_args['Metadata'] = {k: str(v) for k, v in metadata.items()}

        # Run blocking S3 upload in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            partial(
                self.s3.upload_fileobj,
                file,
                self.bucket,
                path,
                ExtraArgs=extra_args
            )
        )

        return path

    async def delete(self, path: str) -> None:
        """Delete file from R2."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            partial(
                self.s3.delete_object,
                Bucket=self.bucket,
                Key=path
            )
        )

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """
        Generate presigned URL for R2 object.

        For public buckets with custom domain, returns direct URL.
        For private buckets, returns presigned URL.
        """
        if self.public_domain:
            # Return public URL if custom domain is configured
            return f"https://{self.public_domain}/{path}"

        # Generate presigned URL for private access
        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(
            None,
            partial(
                self.s3.generate_presigned_url,
                'get_object',
                Params={'Bucket': self.bucket, 'Key': path},
                ExpiresIn=expires_in
            )
        )
        return url

    async def exists(self, path: str) -> bool:
        """Check if object exists in R2."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                partial(
                    self.s3.head_object,
                    Bucket=self.bucket,
                    Key=path
                )
            )
            return True
        except ClientError:
            return False

    async def make_public(self, path: str) -> None:
        """
        Make an object publicly accessible.

        Args:
            path: File path/key to make public
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            partial(
                self.s3.put_object_acl,
                Bucket=self.bucket,
                Key=path,
                ACL='public-read'
            )
        )


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage backend.

    For development and self-hosted deployments.
    """

    def __init__(self, base_path: str = "./media", public_url_base: str = "/media"):
        """
        Initialize local storage backend.

        Args:
            base_path: Base directory for file storage
            public_url_base: Base URL path for accessing files
        """
        self.base_path = base_path
        self.public_url_base = public_url_base
        os.makedirs(base_path, exist_ok=True)

    async def upload(
        self,
        file: BinaryIO,
        path: str,
        content_type: str,
        metadata: Optional[dict] = None
    ) -> str:
        """Save file to local filesystem."""
        full_path = os.path.join(self.base_path, path)

        # Create directory structure
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Write file asynchronously
        async with aiofiles.open(full_path, 'wb') as f:
            content = file.read()
            await f.write(content)

        return path

    async def delete(self, path: str) -> None:
        """Delete file from filesystem."""
        full_path = os.path.join(self.base_path, path)
        if os.path.exists(full_path):
            await asyncio.get_event_loop().run_in_executor(
                None,
                os.remove,
                full_path
            )

    async def get_url(self, path: str, expires_in: int = 3600) -> str:
        """
        Return local file URL.

        Note: Local files don't expire, expires_in is ignored.
        """
        return f"{self.public_url_base}/{path}"

    async def exists(self, path: str) -> bool:
        """Check if file exists on filesystem."""
        full_path = os.path.join(self.base_path, path)
        return os.path.exists(full_path)


class StorageService:
    """
    High-level storage service.

    Provides convenient methods for file operations with automatic
    filename generation, metadata handling, etc.
    """

    def __init__(self, backend: StorageBackend):
        """
        Initialize storage service.

        Args:
            backend: Storage backend instance (R2 or Local)
        """
        self.backend = backend

    def generate_filename(
        self,
        original_filename: str,
        workspace_id: str,
        user_id: str
    ) -> str:
        """
        Generate unique filename with workspace/user organization.

        Format: {workspace_id}/{user_id}/{timestamp}_{hash}{extension}

        Args:
            original_filename: Original upload filename
            workspace_id: Workspace UUID
            user_id: User UUID

        Returns:
            Generated filename path
        """
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        # Create hash for uniqueness
        hash_input = f"{original_filename}{workspace_id}{user_id}{timestamp}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        # Extract extension
        _, ext = os.path.splitext(original_filename)
        ext = ext.lower()

        return f"{workspace_id}/{user_id}/{timestamp}_{hash_value}{ext}"

    async def upload_file(
        self,
        file: BinaryIO,
        original_filename: str,
        content_type: str,
        workspace_id: str,
        user_id: str,
        metadata: Optional[dict] = None
    ) -> Tuple[str, str]:
        """
        Upload file with automatic naming.

        Args:
            file: File object to upload
            original_filename: Original filename
            content_type: MIME type
            workspace_id: Workspace UUID
            user_id: User UUID
            metadata: Optional metadata

        Returns:
            Tuple of (storage_path, generated_filename)
        """
        filename = self.generate_filename(original_filename, workspace_id, user_id)
        storage_path = await self.backend.upload(file, filename, content_type, metadata)
        return storage_path, filename

    async def delete_file(self, path: str) -> None:
        """
        Delete file from storage.

        Args:
            path: File path/key to delete
        """
        await self.backend.delete(path)

    async def get_file_url(self, path: str, expires_in: int = 3600) -> str:
        """
        Get accessible URL for file.

        Args:
            path: File path/key
            expires_in: URL expiration in seconds (for presigned URLs)

        Returns:
            Accessible URL
        """
        return await self.backend.get_url(path, expires_in)

    async def file_exists(self, path: str) -> bool:
        """
        Check if file exists.

        Args:
            path: File path/key

        Returns:
            True if file exists
        """
        return await self.backend.exists(path)


def create_storage_service(
    backend_type: str = "r2",
    **kwargs
) -> StorageService:
    """
    Factory function to create storage service with appropriate backend.

    Args:
        backend_type: "r2" or "local"
        **kwargs: Backend-specific configuration

    Returns:
        Configured StorageService instance

    Example for R2:
        service = create_storage_service(
            backend_type="r2",
            bucket="my-bucket",
            account_id="cf-account-id",
            access_key_id="r2-access-key",
            secret_access_key="r2-secret-key",
            public_domain="media.example.com"  # optional
        )

    Example for Local:
        service = create_storage_service(
            backend_type="local",
            base_path="./media",
            public_url_base="/media"
        )
    """
    if backend_type == "r2":
        backend = CloudflareR2Backend(
            bucket=kwargs.get("bucket"),
            account_id=kwargs.get("account_id"),
            access_key_id=kwargs.get("access_key_id"),
            secret_access_key=kwargs.get("secret_access_key"),
            public_domain=kwargs.get("public_domain")
        )
    elif backend_type == "local":
        backend = LocalStorageBackend(
            base_path=kwargs.get("base_path", "./media"),
            public_url_base=kwargs.get("public_url_base", "/media")
        )
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")

    return StorageService(backend)
