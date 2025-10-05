from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException, status
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import UpdateProfileRequest
from src.api.schema.notification_schema import NotificationPreferencesResponse, UpdateNotificationPreferencesRequest
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.database.database import get_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from datetime import datetime
from pathlib import Path
import time
import os

router = APIRouter()

# Avatar upload directory
AVATAR_UPLOAD_DIR = Path("uploads/avatars")
AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/profile", response_model=dict)
def get_profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current authenticated user's profile

    Returns complete profile information for the logged-in user
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"Fetching profile for user: {user_id}")

        # Get user from database
        db_user = db.query(Users).filter(Users.id == user_id).first()
        if not db_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Build profile response
        profile_data = {
            "id": str(db_user.id),
            "email": db_user.email,
            "username": db_user.username,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "display_name": db_user.display_name,
            "language": db_user.language or "en",
            "timezone": db_user.timezone or "UTC",
            "status": db_user.status,
            "email_verified": db_user.email_verified,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
            "updated_at": db_user.updated_at.isoformat() if db_user.updated_at else None
        }

        logger.info(f"Profile fetched successfully for user: {user_id}")
        return success(
            data={"profile": profile_data},
            request=request,
            message="Profile retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Error fetching profile for user {current_user.get('identity')}: {str(e)}")
        return error(
            message="Failed to fetch profile",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.patch("/profile")
def update_profile(
    request: Request,
    profile_data: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current authenticated user's profile

    - **first_name**: First name
    - **last_name**: Last name
    - **display_name**: Display name
    - **language**: Language preference
    - **timezone**: Timezone preference

    Note: Email, username, and password cannot be changed via this endpoint
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"Profile update requested for user: {user_id}")

        # Get user from database
        db_user = db.query(Users).filter(Users.id == user_id).first()
        if not db_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Track what was updated
        updated_fields = []

        # Update fields if provided
        if profile_data.first_name is not None:
            db_user.first_name = profile_data.first_name
            updated_fields.append("first_name")

        if profile_data.last_name is not None:
            db_user.last_name = profile_data.last_name
            updated_fields.append("last_name")

        if profile_data.display_name is not None:
            db_user.display_name = profile_data.display_name
            updated_fields.append("display_name")

        if profile_data.language is not None:
            db_user.language = profile_data.language
            updated_fields.append("language")

        if profile_data.timezone is not None:
            db_user.timezone = profile_data.timezone
            updated_fields.append("timezone")

        # Update timestamp
        db_user.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(db_user)

        # Build response
        profile_response = {
            "id": str(db_user.id),
            "email": db_user.email,
            "username": db_user.username,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "display_name": db_user.display_name,
            "language": db_user.language,
            "timezone": db_user.timezone,
            "status": db_user.status,
            "email_verified": db_user.email_verified,
            "updated_at": db_user.updated_at.isoformat()
        }

        logger.info(f"Profile updated successfully for user {user_id}. Updated fields: {', '.join(updated_fields)}")
        return success(
            data={
                "profile": profile_response,
                "updated_fields": updated_fields
            },
            request=request,
            message="Profile updated successfully"
        )

    except Exception as e:
        logger.error(f"Error updating profile for user {current_user.get('identity')}: {str(e)}")
        db.rollback()
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
    db: Session = Depends(get_db)
):
    """
    Upload user avatar image.

    - **file**: Image file (JPEG, PNG, GIF, WebP)
    - Max size: 5MB
    - Replaces existing avatar if present
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} uploading avatar")

        # Get user
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

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

        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        # Validate file size (5MB max)
        max_size = 5 * 1024 * 1024  # 5MB
        if file_size > max_size:
            return error(
                message=f"File too large. Max size: 5MB. Your file: {file_size / (1024 * 1024):.2f}MB",
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
                    logger.info(f"Deleted old avatar: {old_avatar_path}")
                except Exception as e:
                    logger.warning(f"Could not delete old avatar: {str(e)}")

        # Generate unique filename
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        timestamp = int(time.time())
        new_filename = f"{user_id}_{timestamp}.{file_extension}"
        file_path = user_avatar_dir / new_filename

        # Save file
        with open(file_path, "wb") as f:
            f.write(file_content)

        # Update user avatar_url (store relative path)
        relative_path = f"/avatars/{user_id}/{new_filename}"
        user.avatar_url = relative_path
        user.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(user)

        logger.info(f"Avatar uploaded successfully for user {user_id}: {relative_path}")

        return success(
            data={
                "avatar_url": user.avatar_url,
                "file_size": file_size,
                "uploaded_at": user.updated_at.isoformat()
            },
            request=request,
            message="Avatar uploaded successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading avatar for user {current_user.get('identity')}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar"
        )


@router.delete("/avatar")
def delete_avatar(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete user avatar.

    Sets avatar_url to null and removes the file from storage.
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"User {user_id} deleting avatar")

        # Get user
        user = db.query(Users).filter(Users.id == user_id).first()
        if not user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

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
                logger.info(f"Deleted avatar file: {avatar_path}")
            except Exception as e:
                logger.warning(f"Could not delete avatar file: {str(e)}")

        # Update user
        old_avatar_url = user.avatar_url
        user.avatar_url = None
        user.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(user)

        logger.info(f"Avatar deleted successfully for user {user_id}")

        return success(
            data={
                "deleted_avatar_url": old_avatar_url,
                "deleted_at": user.updated_at.isoformat()
            },
            request=request,
            message="Avatar deleted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting avatar for user {current_user.get('identity')}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete avatar"
        )


@router.get("/preferences/notifications", response_model=None)
def get_notification_preferences(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's notification preferences.

    Returns default preferences if none exist yet.
    Creates default preferences automatically on first access.

    Returns:
        NotificationPreferencesResponse: User's notification preferences

    Raises:
        500: If database operation fails
    """
    try:
        user_id = current_user.get("identity")

        # Try to get existing preferences
        preferences = db.query(NotificationPreferences).filter(
            NotificationPreferences.user_id == user_id
        ).first()

        # If no preferences exist, create defaults
        if not preferences:
            preferences = NotificationPreferences(user_id=user_id)
            db.add(preferences)
            db.commit()
            db.refresh(preferences)
            logger.info(f"Created default notification preferences for user {user_id}")

        return success(
            data=preferences.to_dict(),
            request=request,
            message="Notification preferences retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get notification preferences for user {current_user.get('identity')}: {str(e)}")
        return error(
            message="Failed to retrieve notification preferences",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.MEDIUM,
            context={"error_details": str(e)},
            request=request
        )


@router.patch("/preferences/notifications", response_model=None)
def update_notification_preferences(
    preferences_update: UpdateNotificationPreferencesRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's notification preferences.

    Creates preferences with default values if they don't exist yet.
    All fields must be provided in the request body.

    Args:
        preferences_update: Notification preferences data

    Returns:
        NotificationPreferencesResponse: Updated notification preferences

    Raises:
        400: If validation fails
        500: If database operation fails
    """
    try:
        user_id = current_user.get("identity")

        # Get or create preferences
        preferences = db.query(NotificationPreferences).filter(
            NotificationPreferences.user_id == user_id
        ).first()

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

        db.commit()
        db.refresh(preferences)

        logger.info(f"Updated notification preferences for user {user_id}")

        return success(
            data=preferences.to_dict(),
            request=request,
            message="Notification preferences updated successfully"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update notification preferences for user {current_user.get('identity')}: {str(e)}")
        return error(
            message="Failed to update notification preferences",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.MEDIUM,
            context={"error_details": str(e)},
            request=request
        )
