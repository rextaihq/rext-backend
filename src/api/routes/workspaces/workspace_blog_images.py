"""Inline blog-image upload route, independent of the removed media library."""

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.rate_limiter import media_upload_rate_limit
from src.api.schema.response.content_responses import BlogImageUploadData
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.config.storage_config import get_allowed_types_by_category
from src.utils.file_upload_utils import validate_and_store_file
from src.utils.response_utils import created
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.storage import storage_service as minio_storage_service

router = APIRouter(tags=["workspace-blog-images"])


@router.post(
    "/{workspace_id}/media/blog-images/upload",
    response_model=SuccessResponse[BlogImageUploadData],
    status_code=status.HTTP_201_CREATED,
)
@db_transaction_handler("upload blog image")
@require_permissions("content.create", "content.update", workspace_scoped=True, require_all=False)
async def upload_blog_image(
    request: Request,
    workspace_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(media_upload_rate_limit()),
):
    """Store an image inserted from the blog editor in MinIO."""
    user_id = str(current_user.get("identity"))
    upload = await validate_and_store_file(
        file=file,
        workspace_id=workspace_id,
        allowed_types=get_allowed_types_by_category("image"),
        max_size_mb=20,
        object_prefix=f"workspaces/{workspace_id}/blog-images/{user_id}",
    )
    return created(
        data={
            "filename": upload["unique_filename"],
            "original_filename": upload["original_filename"],
            "file_type": upload["mime_type"],
            "file_size": upload["size"],
            "storage_backend": "minio",
            "storage_path": upload["secure_path"],
            "storage_bucket": minio_storage_service.bucket_name,
            "public_url": upload["url"],
            "width": upload.get("image_width"),
            "height": upload.get("image_height"),
        },
        request=request,
        message=f"Blog image '{file.filename}' uploaded successfully",
    )
