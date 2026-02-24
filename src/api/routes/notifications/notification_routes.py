from fastapi import APIRouter, Request, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.notification.notification_model import Notification
from src.api.middleware.rate_limiter import notification_read_rate_limit, notification_write_rate_limit
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.route_decorators import require_permissions
from src.utils.logger import logger

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=None)
@require_permissions("user.read", workspace_scoped=False)
async def get_notifications(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit=Depends(notification_read_rate_limit()),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    unread_only: bool = Query(False, description="Filter to only unread notifications"),
    type: Optional[str] = Query(None, description="Filter by notification type"),
    category: Optional[str] = Query(None, description="Filter by notification category"),
    workspace_id: Optional[str] = Query(None, description="Filter by workspace ID"),
):
    """
    Get paginated list of notifications for the current user.
    
    Features:
    - Pagination support
    - Filter by read/unread status
    - Filter by type (workspace, billing, content, knowledge, system)
    - Filter by category (ws_invite_received, billing_payment_failed, etc.)
    - Filter by workspace
    - Excludes deleted and archived notifications by default
    - Returns total count and unread count
    
    Query Parameters:
    - page: Page number (default: 1)
    - limit: Items per page (default: 20, max: 100)
    - unread_only: Show only unread notifications (default: false)
    - type: Filter by notification type
    - category: Filter by notification category
    - workspace_id: Filter by workspace ID
    """
    try:
        user_id = current_user.get("identity")
        
        # Build base query - exclude deleted and archived by default
        base_conditions = [
            Notification.user_id == user_id,
            Notification.active(),
        ]
        
        # Add optional filters
        if unread_only:
            base_conditions.append(Notification.is_read.is_(False))
        
        if type:
            base_conditions.append(Notification.type == type)
        
        if category:
            base_conditions.append(Notification.category == category)
        
        if workspace_id:
            try:
                workspace_uuid = UUID(workspace_id)
                base_conditions.append(Notification.workspace_id == workspace_uuid)
            except ValueError:
                return error(
                    message="Invalid workspace_id format",
                    code=ErrorCode.INVALID_VALUE,
                    status_code=400,
                    severity=ErrorSeverity.LOW,
                    request=request
                )
        
        # Get total count
        count_query = select(func.count(Notification.id)).where(and_(*base_conditions))
        total_result = await db.execute(count_query)
        total_count = total_result.scalar()
        
        # Get unread count
        unread_query = select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
                Notification.active(),
            )
        )
        unread_result = await db.execute(unread_query)
        unread_count = unread_result.scalar()
        
        # Calculate pagination
        offset = (page - 1) * limit
        total_pages = (total_count + limit - 1) // limit if total_count > 0 else 0
        
        # Get notifications with pagination
        notifications_query = (
            select(Notification)
            .where(and_(*base_conditions))
            .order_by(desc(Notification.created_at))
            .offset(offset)
            .limit(limit)
        )
        
        result = await db.execute(notifications_query)
        notifications = result.scalars().all()
        
        # Convert to dict
        notifications_data = [notification.to_dict() for notification in notifications]
        
        logger.info(
            f"Retrieved {len(notifications_data)} notifications for user {user_id} "
            f"(page {page}, total: {total_count}, unread: {unread_count})"
        )
        
        return success(
            data={
                "notifications": notifications_data,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
                "unread_count": unread_count,
            },
            request=request,
            message="Notifications retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error retrieving notifications for user {current_user.get('identity')}: {str(e)}")
        raise


@router.post("/mark-as-read", response_model=None)
@require_permissions("user.update", workspace_scoped=False)
async def mark_notifications_as_read(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit=Depends(notification_write_rate_limit()),
    notification_ids: Optional[List[str]] = Query(None, description="Specific notification IDs to mark as read"),
    mark_all: bool = Query(False, description="Mark all notifications as read"),
):
    """
    Mark notifications as read.
    
    Options:
    - Mark specific notifications by ID
    - Mark all unread notifications
    
    Query Parameters:
    - notification_ids: List of notification IDs to mark as read
    - mark_all: Mark all unread notifications as read (default: false)
    
    Note: You must provide either notification_ids or set mark_all=true
    """
    try:
        user_id = current_user.get("identity")
        
        if not notification_ids and not mark_all:
            return error(
                message="You must provide either notification_ids or set mark_all=true",
                code=ErrorCode.INVALID_VALUE,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )
        
        if mark_all:
            # Mark all unread notifications as read
            query = select(Notification).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read.is_(False),
                    Notification.active(),
                )
            )
            result = await db.execute(query)
            notifications = result.scalars().all()
            
            for notification in notifications:
                notification.mark_as_read()
            
            await db.commit()
            
            logger.info(f"Marked all {len(notifications)} notifications as read for user {user_id}")
            
            return success(
                data={
                    "marked_count": len(notifications),
                    "marked_all": True,
                },
                request=request,
                message=f"Marked {len(notifications)} notifications as read"
            )
        
        else:
            # Mark specific notifications as read
            notification_uuids = []
            for nid in notification_ids:
                try:
                    notification_uuids.append(UUID(nid))
                except ValueError:
                    return error(
                        message=f"Invalid notification ID format: {nid}",
                        code=ErrorCode.INVALID_VALUE,
                        status_code=400,
                        severity=ErrorSeverity.LOW,
                        request=request
                    )
            
            # Get notifications that belong to the user
            query = select(Notification).where(
                and_(
                    Notification.id.in_(notification_uuids),
                    Notification.user_id == user_id,
                    Notification.active(),
                )
            )
            result = await db.execute(query)
            notifications = result.scalars().all()
            
            if not notifications:
                return error(
                    message="No notifications found with the provided IDs",
                    code=ErrorCode.RESOURCE_NOT_FOUND,
                    status_code=404,
                    severity=ErrorSeverity.LOW,
                    request=request
                )
            
            # Mark as read
            for notification in notifications:
                if not notification.is_read:
                    notification.mark_as_read()
            
            await db.commit()
            
            logger.info(f"Marked {len(notifications)} notifications as read for user {user_id}")
            
            return success(
                data={
                    "marked_count": len(notifications),
                    "notification_ids": [str(n.id) for n in notifications],
                },
                request=request,
                message=f"Marked {len(notifications)} notifications as read"
            )
        
    except Exception as e:
        logger.error(f"Error marking notifications as read for user {current_user.get('identity')}: {str(e)}")
        raise


@router.post("/clear", response_model=None)
@require_permissions("user.update", workspace_scoped=False)
async def clear_notifications(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit=Depends(notification_write_rate_limit()),
    notification_ids: Optional[List[str]] = Query(None, description="Specific notification IDs to clear"),
    clear_all_read: bool = Query(False, description="Clear all read notifications"),
):
    """
    Clear (soft delete) notifications.
    
    This endpoint soft deletes notifications, which removes them from the user's view
    but keeps them in the database for audit purposes.
    
    Options:
    - Clear specific notifications by ID
    - Clear all read notifications
    
    Query Parameters:
    - notification_ids: List of notification IDs to clear
    - clear_all_read: Clear all read notifications (default: false)
    
    Note: You must provide either notification_ids or set clear_all_read=true
    """
    try:
        user_id = current_user.get("identity")
        
        if not notification_ids and not clear_all_read:
            return error(
                message="You must provide either notification_ids or set clear_all_read=true",
                code=ErrorCode.INVALID_VALUE,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )
        
        if clear_all_read:
            # Clear all read notifications
            query = select(Notification).where(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read.is_(True),
                    Notification.active(),
                )
            )
            result = await db.execute(query)
            notifications = result.scalars().all()
            
            for notification in notifications:
                notification.soft_delete()
            
            await db.commit()
            
            logger.info(f"Cleared {len(notifications)} read notifications for user {user_id}")
            
            return success(
                data={
                    "cleared_count": len(notifications),
                    "cleared_all_read": True,
                },
                request=request,
                message=f"Cleared {len(notifications)} read notifications"
            )
        
        else:
            # Clear specific notifications
            notification_uuids = []
            for nid in notification_ids:
                try:
                    notification_uuids.append(UUID(nid))
                except ValueError:
                    return error(
                        message=f"Invalid notification ID format: {nid}",
                        code=ErrorCode.INVALID_VALUE,
                        status_code=400,
                        severity=ErrorSeverity.LOW,
                        request=request
                    )
            
            # Get notifications that belong to the user
            query = select(Notification).where(
                and_(
                    Notification.id.in_(notification_uuids),
                    Notification.user_id == user_id,
                    Notification.active(),
                )
            )
            result = await db.execute(query)
            notifications = result.scalars().all()
            
            if not notifications:
                return error(
                    message="No notifications found with the provided IDs",
                    code=ErrorCode.RESOURCE_NOT_FOUND,
                    status_code=404,
                    severity=ErrorSeverity.LOW,
                    request=request
                )
            
            # Soft delete
            for notification in notifications:
                notification.soft_delete()
            
            await db.commit()
            
            logger.info(f"Cleared {len(notifications)} notifications for user {user_id}")
            
            return success(
                data={
                    "cleared_count": len(notifications),
                    "notification_ids": [str(n.id) for n in notifications],
                },
                request=request,
                message=f"Cleared {len(notifications)} notifications"
            )
        
    except Exception as e:
        logger.error(f"Error clearing notifications for user {current_user.get('identity')}: {str(e)}")
        raise


@router.get("/unread-count", response_model=None)
@require_permissions("user.read", workspace_scoped=False)
async def get_unread_count(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit=Depends(notification_read_rate_limit()),
):
    """
    Get the count of unread notifications for the current user.
    
    This is a lightweight endpoint for updating notification badges in the UI.
    """
    try:
        user_id = current_user.get("identity")
        
        # Get unread count
        query = select(func.count(Notification.id)).where(
            and_(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
                Notification.active(),
            )
        )
        result = await db.execute(query)
        unread_count = result.scalar()
        
        return success(
            data={
                "unread_count": unread_count,
            },
            request=request,
            message="Unread count retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting unread count for user {current_user.get('identity')}: {str(e)}")
        raise


@router.get("/{notification_id}", response_model=None)
@require_permissions("user.read", workspace_scoped=False)
async def get_notification_by_id(
    notification_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit=Depends(notification_read_rate_limit()),
):
    """
    Get a specific notification by ID.
    
    Automatically marks the notification as read when retrieved.
    """
    try:
        user_id = current_user.get("identity")
        
        # Validate UUID
        try:
            notification_uuid = UUID(notification_id)
        except ValueError:
            return error(
                message="Invalid notification ID format",
                code=ErrorCode.INVALID_VALUE,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )
        
        # Get notification
        query = select(Notification).where(
            and_(
                Notification.id == notification_uuid,
                Notification.user_id == user_id,
                Notification.active(),
            )
        )
        result = await db.execute(query)
        notification = result.scalar_one_or_none()
        
        if not notification:
            return error(
                message="Notification not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.LOW,
                request=request
            )
        
        # Mark as read if not already read
        if not notification.is_read:
            notification.mark_as_read()
            await db.commit()
            await db.refresh(notification)
        
        return success(
            data={
                "notification": notification.to_dict(),
            },
            request=request,
            message="Notification retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting notification {notification_id} for user {current_user.get('identity')}: {str(e)}")
        raise