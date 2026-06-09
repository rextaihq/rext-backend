import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from typing import Optional, BinaryIO, Union
import io
from pathlib import Path
from src.api.config import get_settings
from src.utils.logger import logger

settings = get_settings()

class StorageService:
    """Service for interacting with MinIO/S3 storage."""

    def __init__(self):
        self.bucket_name = settings.MINIO_BUCKET
        self.available = False
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=f"{'https' if settings.MINIO_USE_SSL else 'http'}://{settings.MINIO_ENDPOINT}",
                aws_access_key_id=settings.MINIO_ACCESS_KEY,
                aws_secret_access_key=settings.MINIO_SECRET_KEY,
                config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}),
                region_name='us-east-1'
            )
            self._ensure_bucket_exists()
            self.available = True
        except Exception as e:
            logger.warning(f"MinIO unavailable: {e}. Storage operations will be skipped.")
            self.available = False

    def _ensure_bucket_exists(self):
        """Checks if the bucket exists and creates it if not."""
        import json
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == '404':
                logger.info(f"Bucket {self.bucket_name} does not exist. Creating...")
                self.s3_client.create_bucket(Bucket=self.bucket_name)
            else:
                logger.error(f"Error checking bucket existence: {str(e)}")
                return

        # Set public-read policy so objects are accessible without presigned URLs
        if settings.MINIO_PUBLIC_URL:
            public_policy = json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{self.bucket_name}/*"]
                }]
            })
            try:
                self.s3_client.put_bucket_policy(
                    Bucket=self.bucket_name,
                    Policy=public_policy
                )
                logger.info(f"Set public-read policy on bucket {self.bucket_name}")
            except Exception as e:
                logger.warning(f"Could not set bucket policy: {str(e)}")

    def upload_file(
        self, 
        file_data: Union[BinaryIO, bytes], 
        object_name: str, 
        content_type: Optional[str] = None
    ) -> Optional[str]:
        """
        Uploads a file to MinIO/S3.
        
        Args:
            file_data: The file content as a binary stream or bytes.
            object_name: The path/name of the object in the bucket.
            content_type: MIME type of the file.
            
        Returns:
            The public URL of the uploaded file if successful, else None.
        """
        if not self.available:
            return None
        try:
            if isinstance(file_data, bytes):
                file_obj = io.BytesIO(file_data)
            else:
                file_obj = file_data

            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            self.s3_client.upload_fileobj(
                file_obj, 
                self.bucket_name, 
                object_name,
                ExtraArgs=extra_args
            )
            
            logger.info(f"Successfully uploaded {object_name} to {self.bucket_name}")
            return self.get_file_url(object_name)
            
        except Exception as e:
            logger.error(f"Failed to upload file {object_name}: {str(e)}")
            return None

    def get_file_url(self, object_name: str, expires_in: int = 3600) -> str:
        """
        Generates a URL for the object. 
        If MINIO_PUBLIC_URL is set, returns a direct link.
        Otherwise, returns a presigned URL.
        """
        if not self.available:
            return ""
        if settings.MINIO_PUBLIC_URL:
            # Direct link if configured (e.g. via Nginx or Cloudflare)
            return f"{settings.MINIO_PUBLIC_URL.rstrip('/')}/{self.bucket_name}/{object_name}"
        
        try:
            # Default to presigned URL for secure access
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_name},
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            logger.error(f"Error generating presigned URL for {object_name}: {str(e)}")
            return ""

    def delete_file(self, object_name: str) -> bool:
        """Deletes an object from MinIO/S3."""
        if not self.available:
            return False
        try:
            # Strip bucket name if it was included in the path (defensive)
            if object_name.startswith(f"/{self.bucket_name}/"):
                object_name = object_name.replace(f"/{self.bucket_name}/", "", 1)
            elif object_name.startswith(f"{self.bucket_name}/"):
                object_name = object_name.replace(f"{self.bucket_name}/", "", 1)
                
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_name)
            logger.info(f"Successfully deleted {object_name} from {self.bucket_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {object_name}: {str(e)}")
            return False

    def download_file(self, object_name: str, local_path: Optional[str] = None) -> Optional[bytes]:
        """
        Downloads a file from MinIO/S3.
        If local_path is provided, saves it there.
        Otherwise, returns the content bytes.
        """
        if not self.available:
            return None
        try:
            if local_path:
                self.s3_client.download_file(self.bucket_name, object_name, local_path)
                return None
            else:
                response = self.s3_client.get_object(Bucket=self.bucket_name, Key=object_name)
                return response['Body'].read()
        except Exception as e:
            logger.error(f"Failed to download file {object_name}: {str(e)}")
            return None

    def check_connection(self) -> bool:
        """Verifies the connection to MinIO/S3 by attempting to head the bucket."""
        if not self.available:
            return False
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except Exception as e:
            logger.error(f"MinIO connection check failed: {str(e)}")
            return False

# Singleton instance
storage_service = StorageService()