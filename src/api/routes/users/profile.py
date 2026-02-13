from fastapi import APIRouter, Depends, Request, UploadFile, File, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path
import io
import filetype
from PIL import Image
from datetime import datetime, timezone

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions, db_transaction_handler
from src.api.schema.user_schema import UpdateProfileRequest, DeactivateAccountRequest, UserResponse, ProfileResponse
from src.api.schema.notification_schema import NotificationPreferencesResponse, UpdateNotificationPreferencesRequest
from src.api.database.async_database import get_async_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import ResourceNotFoundException
from src.services.user_service import UserService
from src.services.notification_preferences_service import NotificationPreferencesService
from src.services.notification_helper import schedule_if_allowed
from datetime import datetime,timezone 

from pathlib import Path
from sqlalchemy import select
import time
import imghdr

router = APIRouter()

# Avatar upload directory - stored in media directory for consistent static file serving
AVATAR_UPLOAD_DIR = Path("media/avatars")
AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.get("/profile", response_model=UserResponse)
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("get profile", auto_commit=False)
async def get_profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """
    Get current authenticated user's profile.
    """
    try:
        user_id = current_user.get("identity")
        service = UserService(db)

        # Get user via service
        user = await service.get_user_by_id(user_id)

        # Build profile response using schema
        profile_data = ProfileResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            display_name=user.display_name,
            bio=user.bio,
            language=user.language or "en",
            timezone=user.timezone or "UTC",
            status=user.status,
            email_verified=user.email_verified,
            avatar_url=user.avatar_url,
            created_at=user.created_at.isoformat() if user.created_at else None,
            updated_at=user.updated_at.isoformat() if user.updated_at else None
        ).model_dump()

        return success(
            data={"profile": profile_data},
            request=request,
            message="Profile retrieved successfully"
        )

    except ResourceNotFoundException:
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error fetching profile: {str(e)}")
        raise


@require_permissions("user.update")
@router.patch("/profile")
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("update profile", auto_commit=True)
async def update_profile(
    request: Request,
    background_tasks: BackgroundTasks,
    profile_data: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """
    Update current authenticated user's profile.
    """
    user_id = current_user.get("identity")
    service = UserService(db)

    # Track what was updated for response
    updated_fields = []
    update_kwargs = {}

    if profile_data.full_name is not None:
        update_kwargs["full_name"] = profile_data.full_name
        updated_fields.append("full_name")
    if profile_data.display_name is not None:
        update_kwargs["display_name"] = profile_data.display_name
        updated_fields.append("display_name")
    if profile_data.bio is not None:
        update_kwargs["bio"] = profile_data.bio
        updated_fields.append("bio")
    if profile_data.language is not None:
        update_kwargs["language"] = profile_data.language
        updated_fields.append("language")
    if profile_data.timezone is not None:
        update_kwargs["timezone"] = profile_data.timezone
        updated_fields.append("timezone")

    if not update_kwargs:
        return success(
            data={"profile": UserResponse.model_validate(await service.get_user_by_id(user_id)).model_dump(), "updated_fields": []},
            request=request,
            message="No changes to update"
        )

    # Update via service
    user = await service.update_profile(user_id=user_id, **update_kwargs)

    # Build response
    profile_response = UserResponse.model_validate(user).model_dump()

    logger.info(f"Profile updated for user {user_id}. Fields: {', '.join(updated_fields)}")

    # Schedule notification
    await schedule_if_allowed(
        db=db,
        user_id=str(user_id),
        background_tasks=background_tasks,
        pref_flag="in_app_notifications",
        message="Your profile has been successfully updated.",
        payload={"user_id": str(user_id), "updated_fields": updated_fields},
        workspace_id=None
    )

    return success(
        data={
            "profile": profile_response,
            "updated_fields": updated_fields
        },
        request=request,
        message="Profile updated successfully"
    )


@router.post("/avatar/upload")
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("upload avatar", auto_commit=True)
async def upload_avatar(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Upload user avatar image.
    Uses filetype and Pillow for secure image validation as per Task 071.
    """
    user_id = current_user.get("identity")
    service = UserService(db)

    # Get user via service
    user = await service.get_user_by_id(user_id)

    # 1. Format validation using MAGIC BYTES
    file_content = await file.read()
    kind = filetype.guess(file_content)
    
    ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    
    if kind is None or kind.mime not in ALLOWED_MIME_TYPES:
        logger.warning(
            f"Invalid image content uploaded by user {user_id}. "
            f"Detected MIME: {kind.mime if kind else 'Unknown'}"
        )
        raise RextValidationException(
            message="Invalid image file. Allowed formats: JPEG, PNG, GIF, WebP."
        )

    # 2. Security: Block SVG files to prevent XSS
    if file.filename and file.filename.lower().endswith('.svg'):
        logger.warning(f"SVG upload attempt blocked for user {user_id}")
        raise RextValidationException(
            message="SVG files are not supported for security reasons."
        )

    # 3. Size validation
    file_size = len(file_content)
    max_size = 5 * 1024 * 1024  # 5MB

    if file_size > max_size:
        raise RextValidationException(
            message=f"File too large. Max: 5MB, Yours: {file_size / (1024 * 1024):.2f}MB"
        )

    # 4. Structural validation with Pillow to ensure it's a valid image
    try:
        img = Image.open(io.BytesIO(file_content))
        img.verify()
    except Exception as e:
        logger.warning(f"Pillow validation failed for user {user_id} upload: {str(e)}")
        raise RextValidationException(
            message="Image file appears to be corrupted or malformed."
        )

    # Create user-specific directory
    user_avatar_dir = AVATAR_UPLOAD_DIR / str(user_id)
    user_avatar_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    file_extension = kind.extension
    filename = f"avatar_{int(datetime.now(timezone.utc).timestamp())}.{file_extension}"
    file_path = user_avatar_dir / filename
    
    with open(file_path, "wb") as f:
        f.write(file_content)

    relative_path = f"/{file_path.as_posix()}"

    # Delete old avatar if exists
    if user.avatar_url:
        try:
            # Resolve the path and check if it's within the upload dir
            old_avatar_path = Path(user.avatar_url.lstrip('/')).resolve()
            base_dir = AVATAR_UPLOAD_DIR.resolve()
            if str(old_avatar_path).startswith(str(base_dir)) and old_avatar_path.exists():
                old_avatar_path.unlink()
        except Exception as e:
            logger.warning(f"Could not delete old avatar: {str(e)}")

    # Update user via service
    updated_user = await service.update_profile(
        user_id=user_id,
        avatar_url=relative_path
    )

    logger.info(f"Avatar updated for user {user_id}: {relative_path}")

    # Schedule notification
    await schedule_if_allowed(
        db=db,
        user_id=str(user_id),
        background_tasks=background_tasks,
        pref_flag="avatar_uploaded",
        message="Your profile picture has been successfully updated.",
        payload={"user_id": str(user_id), "avatar_url": relative_path},
        workspace_id=None
    )

    return success(
        data={
            "avatar_url": relative_path,
            "updated_at": updated_user.updated_at.isoformat()
        },
        request=request,
        message="Avatar uploaded successfully"
    )


@router.delete("/avatar")
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("delete avatar", auto_commit=True)
async def delete_avatar(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Delete user avatar.
    """
    user_id = current_user.get("identity")
    service = UserService(db)

    # Get user via service
    user = await service.get_user_by_id(user_id)

    # Check if user has avatar
    if not user.avatar_url:
        raise ResourceNotFoundException(message="No avatar to delete")

    # Delete file
    try:
        avatar_path = Path(user.avatar_url.lstrip('/')).resolve()
        base_dir = AVATAR_UPLOAD_DIR.resolve()
        if str(avatar_path).startswith(str(base_dir)) and avatar_path.exists():
            avatar_path.unlink()
    except Exception as e:
        logger.warning(f"Could not delete avatar file: {str(e)}")
    # Update user via service
    await service.update_profile(
        user_id=user_id,
        avatar_url=None
    )

    logger.info(f"Avatar deleted for user {user_id}")

    return success(
        request=request,
        message="Avatar deleted successfully"
    )


@router.get("/preferences/notifications")
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("get notification preferences", auto_commit=True)
async def get_notification_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current user's notification preferences.
    Creates default preferences if none exist.
    """
    user_id = current_user.get("identity")

    # Get or create preferences via service
    service = NotificationPreferencesService(db)
    preferences = await service.get_or_create(user_id)

    return success(
        data=preferences.to_dict(),
        request=request,
        message="Notification preferences retrieved successfully"
    )


@router.patch("/preferences/notifications")
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("update notification preferences", auto_commit=True)
async def update_notification_preferences(
    background_tasks: BackgroundTasks,
    preferences_update: UpdateNotificationPreferencesRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update current user's notification preferences.
    """
    user_id = current_user.get("identity")

    # Get or create preferences via service
    notification_service = NotificationPreferencesService(db)
    preferences = await notification_service.get_or_create(user_id)

    # Update preferences dynamically from the request
    update_data = preferences_update.model_dump(exclude_unset=True)

    # Handle simplified categories if provided
    if "categories" in update_data:
        categories = update_data.pop("categories")
        if isinstance(categories, dict):
            # Mapping of categories to DB fields
            mapping = {
                "workspace_invites": ["ws_invite_received"],
            }

            for cat, value in categories.items():
                if cat in mapping:
                    for db_field in mapping[cat]:
                        if hasattr(preferences, db_field):
                            setattr(preferences, db_field, value)
                            logger.debug(f"Updated category preference '{cat}' -> '{db_field}' to {value}")

    # Handle all other fields directly
    for field, value in update_data.items():
        if hasattr(preferences, field):
            setattr(preferences, field, value)
            logger.debug(f"Updated notification preference '{field}' for user {user_id}")

    await db.flush()

    # Schedule notification
    await schedule_if_allowed(
        db=db,
        user_id=str(user_id),
        background_tasks=background_tasks,
        pref_flag="in_app_notifications",
        message="Your notification preferences have been successfully updated.",
        payload={"user_id": str(user_id)},
        workspace_id=None
    )

    return success(
        data=preferences.to_dict(),
        request=request,
        message="Notification preferences updated successfully"
    )

