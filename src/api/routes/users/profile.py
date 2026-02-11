from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession


from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions, db_transaction_handler
from src.api.schema.user_schema import UpdateProfileRequest
from src.api.schema.notification_schema import NotificationPreferencesResponse, UpdateNotificationPreferencesRequest
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
from src.services.user_service import UserService
from src.services.notification_helper import schedule_if_allowed
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from datetime import datetime, timezone,timezone 

from pathlib import Path
from sqlalchemy import select
import time
import filetype
from PIL import Image
import io

router = APIRouter()

# Avatar upload directory - stored in media directorys for consistent static file serving
AVATAR_UPLOAD_DIR = Path("media/avatars")
AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@require_permissions("user.read")
@router.get("/profile", response_model=dict)
@db_transaction_handler("get profile", auto_commit=False)
async def get_profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current authenticated user's profile.
    Uses UserService for business logic.
    """
    user_id = current_user.get("identity")
    service = UserService(db)

    # Get user via service
    user = await service.get_user_by_id(user_id)

    # Build profile response
    return {
        "profile": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
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
    }


@require_permissions("user.update")
@router.patch("/profile")
@db_transaction_handler("update profile", auto_commit=True)
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

    if not updated_fields:
        raise RextValidationException(message="No fields provided for update")

    # Update via service
    user = await service.update_profile(user_id=user_id, **update_kwargs)

    # Build response
    profile_response = {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
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


@router.post("/avatar/upload")
@require_permissions("user.update")
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
    Avatar management could be extracted to UserService in future.
    """
    user_id = current_user.get("identity")
    service = UserService(db)

    # Get user via service
    user = await service.get_user_by_id(user_id)

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        return error(
            message=f"Invalid file type. Allowed: {', '.join(allowed_types)}",
            code=ErrorCode.INVALID_VALUE,
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
            code=ErrorCode.INVALID_VALUE,
            status_code=400,
            severity=ErrorSeverity.LOW,
            request=request
        )

    # Validate actual file content using magic bytes (not just Content-Type header)
    ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}

    detected_mime = filetype.guess_mime(file_content)

    if detected_mime is None or detected_mime not in ALLOWED_MIME_TYPES:
        logger.warning(
            f"Invalid image file uploaded by user {user_id}. "
            f"Content-Type: {file.content_type}, Detected MIME: {detected_mime}",
            extra={"user_id": str(user_id)}
        )
        return error(
            message="Invalid image file. File content does not match an allowed image format (JPEG, PNG, GIF, WebP).",
            code=ErrorCode.INVALID_VALUE,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )

    # Structural validation: verify the file is a parseable image, not just valid magic bytes
    try:
        img = Image.open(io.BytesIO(file_content))
        img.verify()
    except Exception:
        logger.warning(
            f"Corrupted or malformed image uploaded by user {user_id}. "
            f"Content-Type: {file.content_type}, Detected MIME: {detected_mime}",
            extra={"user_id": str(user_id)}
        )
        return error(
            message="Image file appears to be corrupted or malformed.",
            code=ErrorCode.INVALID_VALUE,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            request=request
        )

    # Security: Block SVG files to prevent XSS
    if file.filename and file.filename.lower().endswith('.svg'):
        logger.warning(f"SVG upload attempt blocked for user {user_id}")
        raise RextValidationException(
            message="SVG files are not supported for security reasons."
        )

    # Create user-specific directory
    user_avatar_dir = AVATAR_UPLOAD_DIR / str(user_id)
    user_avatar_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    file_extension = Path(file.filename).suffix
    if not file_extension:
        # Map detected mime to extension
        mime_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp"
        }
        file_extension = mime_map.get(detected_mime, ".jpg")

    file_name = f"avatar_{int(time.time())}{file_extension}"
    file_path = user_avatar_dir / file_name

    # Save file
    with open(file_path, "wb") as f:
        f.write(file_content)

    relative_path = f"/media/avatars/{user_id}/{file_name}"

    # Delete old avatar if it exists
    if user.avatar_url:
        old_avatar_url = user.avatar_url
        # Remove leading slash for Path
        old_avatar_path = Path(old_avatar_url.lstrip('/')).resolve()
        
        # Security: Validate path is within allowed directory to prevent path traversal
        try:
            # Resolve the upload dir to compare absolute paths
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
@require_permissions("user.update")
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

    # Delete file from storage with path traversal protection
    avatar_path = Path(user.avatar_url.lstrip('/')).resolve()
    try:
        avatar_path.relative_to(AVATAR_UPLOAD_DIR.resolve())
        if avatar_path.exists():
            avatar_path.unlink()
    except (ValueError, Exception) as e:
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

    logger.info(f"Avatar deleted for user {user_id}")

    # Schedule notification
    await schedule_if_allowed(
        db=db,
        user_id=str(user_id),
        background_tasks=background_tasks,
        pref_flag="in_app_notifications",
        message="Your profile picture has been successfully deleted.",
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


@router.get("/preferences/notifications", response_model=None)
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

    Note: Notification preferences logic kept in route for now.
    Could be extracted to NotificationService in future refactor.
    """
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
        logger.info(f"Created default notification preferences for user {user_id}")

    return preferences.to_dict()


@router.patch("/preferences/notifications", response_model=None)
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
    Creates preferences with defaults if they don't exist.

    Supports partial updates - only provided fields will be updated.
    """
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

    # Update preferences dynamically from the request
    update_data = preferences_update.model_dump(exclude_unset=True)

    # Handle simplified categories if provided
    if "categories" in update_data:
        categories = update_data.pop("categories")
        # Mapping of categories to DB fields (applies to both email and in-app)
        mapping = {
            "mentions": ["email_mentions", "in_app_mentions"],
            "workspace_invites": ["ws_invite_received"],
            "content_updates": ["email_content_updates", "in_app_content_updates"],
            "comments": ["email_comments", "in_app_comments"],
            "team_activity": ["email_team_activity", "in_app_team_activity"],
            "security_alerts": ["email_security_alerts", "in_app_security_alerts"],
            "billing_updates": ["email_billing_updates", "in_app_billing_updates"],
            "product_updates": ["email_product_updates", "in_app_product_updates"],
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

from src.api.schema.user_schema import DeactivateAccountRequest

@router.post("/deactivate")
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("deactivate account", auto_commit=True)
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
    from datetime import timedelta
    from src.api.models.subscription_models.subscriptions import UserSubscription

    user_id = current_user.get("identity")
    service = UserService(db)

    # Validate confirmation
    if not deactivate_request.confirm:
        return error(
            message="You must confirm account deactivation",
            code=ErrorCode.INVALID_VALUE,
            status_code=400,
            severity=ErrorSeverity.LOW,
            request=request
        )

    # Verify password before allowing deactivation
    if not await service.verify_user_password(user_id, deactivate_request.password):
        logger.warning(f"Failed deactivation attempt for user {user_id}: invalid password")
        return error(
            message="Invalid password. Please enter your current password to deactivate your account.",
            code=ErrorCode.UNAUTHORIZED,
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
            code=ErrorCode.INVALID_VALUE,
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
            subscription.canceled_at = datetime.now(timezone.utc)
            logger.info(f"Canceled subscription {subscription.id} for user {user_id}")

    # Deactivate user account
    now = datetime.now(timezone.utc)
    scheduled_deletion = now + timedelta(days=14)

    user.status = "inactive"
    user.deactivated_at = now

    # Log the deactivation reason if provided
    if deactivate_request.reason:
        logger.info(f"User {user_id} deactivated account. Reason: {deactivate_request.reason}")
    else:
        logger.info(f"User {user_id} deactivated account")

    # The decorator handles the commit
    
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
