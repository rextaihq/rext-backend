from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions
from src.api.schema.user_schema import UpdateProfileRequest, DeactivateAccountRequest
from src.api.schema.notification_schema import NotificationPreferencesResponse, UpdateNotificationPreferencesRequest
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.database.async_database import get_async_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import ResourceNotFoundException
from src.services.user_service import UserService
from src.services.notification_helper import schedule_if_allowed
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
import time
import imghdr

router = APIRouter()

# Avatar upload directory - stored in media directorys for consistent static file serving
AVATAR_UPLOAD_DIR = Path("media/avatars")
AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@require_permissions("user.read")
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
            "bio": user.bio,
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
        raise


@require_permissions("user.update")
@router.patch("/profile")
async def update_profile(
    request: Request,
    background_tasks: BackgroundTasks,
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
        if profile_data.bio is not None:
            update_kwargs["bio"] = profile_data.bio
            updated_fields.append("bio")
        if profile_data.language is not None:
            update_kwargs["language"] = profile_data.language
            updated_fields.append("language")
        if profile_data.timezone is not None:
            update_kwargs["timezone"] = profile_data.timezone
            updated_fields.append("timezone")

        # Update via service
        user = await service.update_profile(user_id=user_id, **update_kwargs)

        # Commit changes to database
        await db.commit()

        # Build response
        profile_response = {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "display_name": user.display_name,
            "bio": user.bio,
            "language": user.language,
            "timezone": user.timezone,
            "status": user.status,
            "email_verified": user.email_verified,
            "avatar_url": user.avatar_url,
            "updated_at": user.updated_at.isoformat()
        }

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
        # Schedule failure notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message=f"Failed to update profile: {str(e)}",
            payload={"user_id": str(user_id), "error": str(e)},
            workspace_id=None,
            title="Profile Update Failed",
            status="error"
        )
        raise


@router.post("/avatar/upload")
@require_permissions("user.update")
async def upload_avatar(
    request: Request,
    background_tasks: BackgroundTasks,
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

        # Validate actual file content using magic bytes (not just Content-Type header)
        image_type = imghdr.what(None, file_content)
        allowed_image_types = ['jpeg', 'png', 'gif', 'webp']

        if image_type not in allowed_image_types:
            logger.warning(
                f"Invalid image file uploaded by user {user_id}. " +
                f"Content-Type: {file.content_type}, Actual type: {image_type}",
                extra={"user_id": str(user_id)}
            )
            return error(
                message="Invalid image file. File content does not match an allowed image format (JPEG, PNG, GIF, WebP).",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Security: Block SVG files to prevent XSS
        if file.filename and file.filename.lower().endswith('.svg'):
            logger.warning(f"SVG upload attempt blocked for user {user_id}")
            return error(
                message="SVG files are not supported for security reasons.",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Create user-specific directory
        user_avatar_dir = AVATAR_UPLOAD_DIR / str(user_id)
        user_avatar_dir.mkdir(parents=True, exist_ok=True)

        # Delete old avatar if exists
        if user.avatar_url:
            # Construct correct path: DB stores "/media/avatars/..." and files are in "media/avatars/..."
            old_avatar_path = Path(user.avatar_url.lstrip('/')).resolve()

            # Security: Validate path is within allowed directory to prevent path traversal
            try:
                old_avatar_path.relative_to(AVATAR_UPLOAD_DIR.resolve())
                if old_avatar_path.exists():
                    old_avatar_path.unlink()
            except (ValueError, Exception) as e:
                # Path is outside allowed directory or deletion failed
                if isinstance(e, ValueError):
                    logger.warning(
                        f"Path traversal attempt detected for user {user_id}: {user.avatar_url}",
                        extra={"user_id": str(user_id), "attempted_path": user.avatar_url}
                    )
                else:
                    logger.warning(f"Could not delete old avatar: {str(e)}")

        # Save new avatar
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        timestamp = int(time.time())
        new_filename = f"{user_id}_{timestamp}.{file_extension}"
        file_path = user_avatar_dir / new_filename

        with open(file_path, "wb") as f:
            f.write(file_content)

        # Update user avatar via service
        relative_path = f"/media/avatars/{user_id}/{new_filename}"
        updated_user = await service.update_profile(
            user_id=user_id,
            avatar_url=relative_path
        )

        # Commit changes to database
        await db.commit()

        logger.info(f"Avatar uploaded for user {user_id}: {relative_path}")

        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="Your profile has been successfully updated.",
            payload={"user_id": str(user_id)},
            workspace_id=None
        )

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
        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="failed to upload avatar",
            payload={"user_id": str(user_id), "error": str(e)},
            workspace_id=None
        )
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error uploading avatar: {str(e)}")
        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="failed to upload avatar",
            payload={"user_id": str(user_id), "error": str(e)},
            workspace_id=None
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar"
        )


@router.delete("/avatar")
@require_permissions("user.update")
async def delete_avatar(
    request: Request,
    background_tasks: BackgroundTasks,
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

        # Delete file from storage with path traversal protection
        # Construct correct path: DB stores "/media/avatars/..." and files are in "media/avatars/..."
        avatar_path = Path(user.avatar_url.lstrip('/')).resolve()

        try:
            # Security: Validate path is within allowed directory
            avatar_path.relative_to(AVATAR_UPLOAD_DIR.resolve())
            if avatar_path.exists():
                avatar_path.unlink()
        except (ValueError, Exception) as e:
            # Path is outside allowed directory or deletion failed
            if isinstance(e, ValueError):
                logger.warning(
                    f"Path traversal attempt detected for user {user_id}: {user.avatar_url}",
                    extra={"user_id": str(user_id), "attempted_path": user.avatar_url}
                )
            else:
                logger.warning(f"Could not delete avatar file: {str(e)}")

        # Update user via service
        old_avatar_url = user.avatar_url
        updated_user = await service.update_profile(
            user_id=user_id,
            avatar_url=None
        )

        # Commit changes to database
        await db.commit()

        logger.info(f"Avatar deleted for user {user_id}")

        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="Your profile has been successfully deleted.",
            payload={"user_id": str(user_id)},
            workspace_id=None
        )

        return success(
            data={
                "deleted_avatar_url": old_avatar_url,
                "deleted_at": updated_user.updated_at.isoformat()
            },
            request=request,
            message="Avatar deleted successfully"
        )

    except ResourceNotFoundException:
        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="failed to delete avatar",
            payload={"user_id": str(user_id), "error": str(e)},
            workspace_id=None
        )
        return error(
            message="User not found",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )
    except Exception as e:
        logger.error(f"Error deleting avatar: {str(e)}")
        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="failed to delete avatar",
            payload={"user_id": str(user_id), "error": str(e)},
            workspace_id=None
        )
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete avatar"
        )


@router.get("/preferences/notifications", response_model=None)
@require_permissions("user.read", workspace_scoped=False)
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
            await db.commit()
            await db.refresh(preferences)
            logger.info(f"Created default notification preferences for user {user_id}")

        return success(
            data=preferences.to_dict(),
            request=request,
            message="Notification preferences retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Failed to get notification preferences: {str(e)}")
        raise


@router.patch("/preferences/notifications", response_model=None)
@require_permissions("user.update", workspace_scoped=False)
async def update_notification_preferences(
    background_tasks: BackgroundTasks,
    preferences_update: UpdateNotificationPreferencesRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update current user's notification preferences.
    Creates preferences with defaults if they don't exist.

    Supports partial updates - only provided fields will be updated.
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

        # Update global toggles
        if preferences_update.email_notifications is not None:
            preferences.email_notifications = preferences_update.email_notifications

        if preferences_update.in_app_notifications is not None:
            preferences.in_app_notifications = preferences_update.in_app_notifications

        # Update workspace notifications
        if preferences_update.ws_invite_received is not None:
            preferences.ws_invite_received = preferences_update.ws_invite_received
        if preferences_update.ws_invite_accepted is not None:
            preferences.ws_invite_accepted = preferences_update.ws_invite_accepted
        if preferences_update.ws_role_changed is not None:
            preferences.ws_role_changed = preferences_update.ws_role_changed
        if preferences_update.ws_member_removed is not None:
            preferences.ws_member_removed = preferences_update.ws_member_removed

        # Update content generation notifications
        if preferences_update.gen_started is not None:
            preferences.gen_started = preferences_update.gen_started
        if preferences_update.gen_completed is not None:
            preferences.gen_completed = preferences_update.gen_completed
        if preferences_update.gen_failed is not None:
            preferences.gen_failed = preferences_update.gen_failed
        if preferences_update.gen_published is not None:
            preferences.gen_published = preferences_update.gen_published

        # Update billing notifications
        if preferences_update.billing_payment_success is not None:
            preferences.billing_payment_success = preferences_update.billing_payment_success
        if preferences_update.billing_payment_failed is not None:
            preferences.billing_payment_failed = preferences_update.billing_payment_failed
        if preferences_update.billing_subscription_cancelled is not None:
            preferences.billing_subscription_cancelled = preferences_update.billing_subscription_cancelled
        if preferences_update.billing_subscription_expiring is not None:
            preferences.billing_subscription_expiring = preferences_update.billing_subscription_expiring
        if preferences_update.billing_trial_ending is not None:
            preferences.billing_trial_ending = preferences_update.billing_trial_ending
        if preferences_update.billing_usage_limit_warning is not None:
            preferences.billing_usage_limit_warning = preferences_update.billing_usage_limit_warning
        if preferences_update.billing_usage_limit_exceeded is not None:
            preferences.billing_usage_limit_exceeded = preferences_update.billing_usage_limit_exceeded

        # Update knowledge base notifications
        if preferences_update.kb_processing_completed is not None:
            preferences.kb_processing_completed = preferences_update.kb_processing_completed
        if preferences_update.kb_processing_failed is not None:
            preferences.kb_processing_failed = preferences_update.kb_processing_failed

        # Update digest settings
        if preferences_update.digest_enabled is not None:
            preferences.digest_enabled = preferences_update.digest_enabled
        if preferences_update.digest_frequency is not None:
            preferences.digest_frequency = preferences_update.digest_frequency

        # Update marketing settings
        if preferences_update.marketing_updates is not None:
            preferences.marketing_updates = preferences_update.marketing_updates

        # Commit changes to database
        await db.commit()

        logger.info(f"Updated notification preferences for user {user_id}")
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

    except Exception as e:
        logger.error(f"Failed to update notification preferences: {str(e)}")
        # Schedule notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user_id),
            background_tasks=background_tasks,
            pref_flag="in_app_notifications",
            message="failed to update notification preferences",
            payload={"user_id": str(user_id), "error": str(e)},
            workspace_id=None
        )
        raise


@router.post("/deactivate")
@require_permissions("user.update", workspace_scoped=False)
async def deactivate_account(
    request: Request,
    deactivate_request: DeactivateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Deactivate current user's account.

    This will:
    1. Set the account status to 'deactivated'
    2. Set deactivated_at timestamp
    3. Optionally cancel active subscriptions
    4. Schedule account for deletion in 14 days

    The user can reactivate their account within 14 days by logging in.
    After 14 days, the account will be permanently deleted.
    """
    try:
        from datetime import timedelta
        from src.api.models.subscription_models.subscriptions import UserSubscription

        user_id = current_user.get("identity")
        service = UserService(db)

        # Validate confirmation
        if not deactivate_request.confirm:
            return error(
                message="You must confirm account deactivation",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Verify password before allowing deactivation
        if not await service.verify_user_password(user_id, deactivate_request.password):
            logger.warning(f"Failed deactivation attempt for user {user_id}: invalid password")
            return error(
                message="Invalid password. Please enter your current password to deactivate your account.",
                code=ErrorCode.AUTHENTICATION_ERROR,
                status_code=401,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        # Get user
        user = await service.get_user_by_id(user_id)

        # Check if already deactivated
        if user.status == "inactive":
            return error(
                message="Account is already deactivated",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Handle subscription cancellation if requested
        if deactivate_request.cancel_subscriptions:
            # Get active subscriptions
            subscriptions_result = await db.execute(
                select(UserSubscription)
                .where(UserSubscription.user_id == user_id)
                .where(UserSubscription.status.in_(["active", "trialing"]))
            )
            active_subscriptions = subscriptions_result.scalars().all()

            for subscription in active_subscriptions:
                subscription.status = "canceled"
                subscription.canceled_at = datetime.utcnow()
                logger.info(f"Canceled subscription {subscription.id} for user {user_id}")

        # Deactivate user account
        now = datetime.utcnow()
        scheduled_deletion = now + timedelta(days=14)

        user.status = "inactive"
        user.deactivated_at = now

        # Log the deactivation reason if provided
        if deactivate_request.reason:
            logger.info(f"User {user_id} deactivated account. Reason: {deactivate_request.reason}")
        else:
            logger.info(f"User {user_id} deactivated account")

        # Commit changes
        await db.commit()

        return success(
            data={
                "success": True,
                "user_id": str(user.id),
                "email": user.email,
                "status": user.status,
                "deactivated_at": user.deactivated_at.isoformat(),
                "scheduled_deletion_at": scheduled_deletion.isoformat(),
                "message": "Your account has been deactivated and will be deleted in 14 days."
            },
            request=request,
            message="Account deactivated successfully"
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
        logger.error(f"Error deactivating account for user {current_user.get('identity')}: {str(e)}")
        raise
