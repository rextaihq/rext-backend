from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import UpdateProfileRequest
from src.api.schema.notification_schema import NotificationPreferencesResponse, UpdateNotificationPreferencesRequest
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.database.async_database import get_async_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import ResourceNotFoundException
from src.services.user_service import UserService
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
import time

router = APIRouter()

# Avatar upload directory
AVATAR_UPLOAD_DIR = Path("uploads/avatars")
AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/profile", response_model=dict)
async def get_profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current authenticated user's profile.
    Uses UserService for business logic.
    """
    try:
        user_id = current_user.get("identity")
        service = UserService(db)

        # Get user via service
        user = await service.get_user_by_id(user_id)

        # Build profile response
        profile_data = {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "display_name": user.display_name,
            "language": user.language or "en",
            "timezone": user.timezone or "UTC",
            "status": user.status,
            "email_verified": user.email_verified,
            "avatar_url": user.avatar_url,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None
        }

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
        return error(
            message="Failed to fetch profile",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.patch("/profile")
async def update_profile(
    request: Request,
    profile_data: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update current authenticated user's profile.
    Uses UserService for business logic.
    """
    try:
        user_id = current_user.get("identity")
        service = UserService(db)

        # Track what was updated for response
        updated_fields = []
        update_kwargs = {}

        if profile_data.first_name is not None:
            update_kwargs["first_name"] = profile_data.first_name
            updated_fields.append("first_name")
        if profile_data.last_name is not None:
            update_kwargs["last_name"] = profile_data.last_name
            updated_fields.append("last_name")
        if profile_data.display_name is not None:
            update_kwargs["display_name"] = profile_data.display_name
            updated_fields.append("display_name")
        if profile_data.language is not None:
            update_kwargs["language"] = profile_data.language
            updated_fields.append("language")
        if profile_data.timezone is not None:
            update_kwargs["timezone"] = profile_data.timezone
            updated_fields.append("timezone")

        # Update via service
        user = await service.update_profile(user_id=user_id, **update_kwargs)

        # Build response
        profile_response = {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "display_name": user.display_name,
            "language": user.language,
            "timezone": user.timezone,
            "status": user.status,
            "email_verified": user.email_verified,
            "updated_at": user.updated_at.isoformat()
        }

        logger.info(f"Profile updated for user {user_id}. Fields: {', '.join(updated_fields)}")
        return success(
            data={
                "profile": profile_response,
                "updated_fields": updated_fields
            },
            request=request,
            message="Profile updated successfully"
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
        logger.error(f"Error updating profile: {str(e)}")
        return error(
            message="Failed to update profile",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/avatar/upload")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Upload user avatar image.
    Avatar management could be extracted to UserService in future.
    """
    try:
        user_id = current_user.get("identity")
        service = UserService(db)

        # Get user via service
        user = await service.get_user_by_id(user_id)

        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if file.content_type not in allowed_types:
            return error(
                message=f"Invalid file type. Allowed: {', '.join(allowed_types)}",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Read and validate file
        file_content = await file.read()
        file_size = len(file_content)
        max_size = 5 * 1024 * 1024  # 5MB

        if file_size > max_size:
            return error(
                message=f"File too large. Max: 5MB, Yours: {file_size / (1024 * 1024):.2f}MB",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Create user-specific directory
        user_avatar_dir = AVATAR_UPLOAD_DIR / str(user_id)
        user_avatar_dir.mkdir(parents=True, exist_ok=True)

        # Delete old avatar if exists
        if user.avatar_url:
            old_avatar_path = Path(user.avatar_url.lstrip('/'))
            if old_avatar_path.exists():
                try:
                    old_avatar_path.unlink()
                except Exception as e:
                    logger.warning(f"Could not delete old avatar: {str(e)}")

        # Save new avatar
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        timestamp = int(time.time())
        new_filename = f"{user_id}_{timestamp}.{file_extension}"
        file_path = user_avatar_dir / new_filename

        with open(file_path, "wb") as f:
            f.write(file_content)

        # Update user avatar via service
        relative_path = f"/avatars/{user_id}/{new_filename}"
        updated_user = await service.update_profile(
            user_id=user_id,
            avatar_url=relative_path
        )

        logger.info(f"Avatar uploaded for user {user_id}: {relative_path}")

        return success(
            data={
                "avatar_url": updated_user.avatar_url,
                "file_size": file_size,
                "uploaded_at": updated_user.updated_at.isoformat()
            },
            request=request,
            message="Avatar uploaded successfully"
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
        logger.error(f"Error uploading avatar: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar"
        )


@router.delete("/avatar")
async def delete_avatar(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Delete user avatar.
    """
    try:
        user_id = current_user.get("identity")
        service = UserService(db)

        # Get user via service
        user = await service.get_user_by_id(user_id)

        # Check if user has avatar
        if not user.avatar_url:
            return error(
                message="No avatar to delete",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Delete file from storage
        avatar_path = Path(user.avatar_url.lstrip('/'))
        if avatar_path.exists():
            try:
                avatar_path.unlink()
            except Exception as e:
                logger.warning(f"Could not delete avatar file: {str(e)}")

        # Update user via service
        old_avatar_url = user.avatar_url
        updated_user = await service.update_profile(
            user_id=user_id,
            avatar_url=None
        )

        logger.info(f"Avatar deleted for user {user_id}")

        return success(
            data={
                "deleted_avatar_url": old_avatar_url,
                "deleted_at": updated_user.updated_at.isoformat()
            },
            request=request,
            message="Avatar deleted successfully"
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
        logger.error(f"Error deleting avatar: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete avatar"
        )


@router.get("/preferences/notifications", response_model=None)
async def get_notification_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current user's notification preferences.
    Creates default preferences if none exist.

    Note: Notification preferences logic kept in route for now.
    Could be extracted to NotificationService in future refactor.
    """
    try:
        user_id = current_user.get("identity")

        # Get existing preferences
        result = await db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user_id
            )
        )
        preferences = result.scalar_one_or_none()

        # Create defaults if needed
        if not preferences:
            preferences = NotificationPreferences(user_id=user_id)
            db.add(preferences)
            await db.flush()
            await db.refresh(preferences)
            logger.info(f"Created default notification preferences for user {user_id}")

        return success(
            data=preferences.to_dict(),
            request=request,
            message="Notification preferences retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Failed to get notification preferences: {str(e)}")
        return error(
            message="Failed to retrieve notification preferences",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.MEDIUM,
            context={"error_details": str(e)},
            request=request
        )


@router.patch("/preferences/notifications", response_model=None)
async def update_notification_preferences(
    preferences_update: UpdateNotificationPreferencesRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update current user's notification preferences.
    Creates preferences with defaults if they don't exist.
    """
    try:
        user_id = current_user.get("identity")

        # Get or create preferences
        result = await db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.user_id == user_id
            )
        )
        preferences = result.scalar_one_or_none()

        if not preferences:
            preferences = NotificationPreferences(user_id=user_id)
            db.add(preferences)
            logger.info(f"Creating notification preferences for user {user_id}")

        # Update all fields
        preferences.email_notifications = preferences_update.emailNotifications
        preferences.email_digest_frequency = preferences_update.emailDigestFrequency
        preferences.email_workspace_invites = preferences_update.emailWorkspaceInvites
        preferences.email_comments = preferences_update.emailComments
        preferences.email_mentions = preferences_update.emailMentions
        preferences.email_updates = preferences_update.emailUpdates
        preferences.in_app_notifications = preferences_update.inAppNotifications
        preferences.in_app_workspace_invites = preferences_update.inAppWorkspaceInvites
        preferences.in_app_comments = preferences_update.inAppComments
        preferences.in_app_mentions = preferences_update.inAppMentions
        preferences.in_app_updates = preferences_update.inAppUpdates

        await db.flush()
        await db.refresh(preferences)

        logger.info(f"Updated notification preferences for user {user_id}")

        return success(
            data=preferences.to_dict(),
            request=request,
            message="Notification preferences updated successfully"
        )

    except Exception as e:
        logger.error(f"Failed to update notification preferences: {str(e)}")
        return error(
            message="Failed to update notification preferences",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.MEDIUM,
            context={"error_details": str(e)},
            request=request
        )
