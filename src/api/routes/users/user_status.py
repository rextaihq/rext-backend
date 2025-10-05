from fastapi import APIRouter, Depends, Request, HTTPException, status
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.user_schema import (
    UserStatusRequest,
    UserStatusResponse,
    DeactivateAccountRequest,
    DeactivateAccountResponse
)
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.api.database.database import get_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.utils.audit_helper import create_audit_log
from src.api.middleware.permissions import is_admin
from datetime import datetime, timedelta

router = APIRouter()


@router.post("/{user_id}/suspend", response_model=UserStatusResponse)
def suspend_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Suspend a user account (admin only).

    - **user_id**: ID of the user to suspend
    - **reason**: Optional reason for suspension

    Requires admin privileges.
    """
    try:
        # Check if current user is admin
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        # Get target user
        target_user = db.query(Users).filter(Users.id == user_id).first()
        if not target_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Store old status
        old_status = target_user.status

        # Update status
        target_user.status = "suspended"
        target_user.updated_at = datetime.utcnow()

        # Create audit log
        admin_user_id = current_user.get("identity")
        admin_user = db.query(Users).filter(Users.id == admin_user_id).first()

        create_audit_log(
            db=db,
            user_id=admin_user_id,
            action="user.suspend",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "suspended", "reason": status_data.reason},
            request=request,
            username=admin_user.username if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        db.commit()
        db.refresh(target_user)

        logger.info(f"User {user_id} suspended by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            username=target_user.username,
            email=target_user.email,
            old_status=old_status,
            new_status="suspended",
            changed_by=admin_user.username if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message=f"User {target_user.username} suspended successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error suspending user {user_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to suspend user"
        )


@router.post("/{user_id}/activate", response_model=UserStatusResponse)
def activate_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Activate a suspended or banned user account (admin only).

    - **user_id**: ID of the user to activate
    - **reason**: Optional reason for activation

    Requires admin privileges.
    """
    try:
        # Check if current user is admin
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        # Get target user
        target_user = db.query(Users).filter(Users.id == user_id).first()
        if not target_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Store old status
        old_status = target_user.status

        # Update status
        target_user.status = "active"
        target_user.updated_at = datetime.utcnow()

        # Create audit log
        admin_user_id = current_user.get("identity")
        admin_user = db.query(Users).filter(Users.id == admin_user_id).first()

        create_audit_log(
            db=db,
            user_id=admin_user_id,
            action="user.activate",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "active", "reason": status_data.reason},
            request=request,
            username=admin_user.username if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        db.commit()
        db.refresh(target_user)

        logger.info(f"User {user_id} activated by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            username=target_user.username,
            email=target_user.email,
            old_status=old_status,
            new_status="active",
            changed_by=admin_user.username if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message=f"User {target_user.username} activated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating user {user_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate user"
        )


@router.post("/{user_id}/ban", response_model=UserStatusResponse)
def ban_user(
    user_id: str,
    request: Request,
    status_data: UserStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ban a user account (admin only).

    - **user_id**: ID of the user to ban
    - **reason**: Optional reason for ban

    Requires admin privileges.
    """
    try:
        # Check if current user is admin
        if not is_admin(current_user):
            return error(
                message="Insufficient permissions. Admin role required.",
                code=ErrorCode.PERMISSION_DENIED,
                status_code=403,
                severity=ErrorSeverity.HIGH,
                request=request
            )

        # Get target user
        target_user = db.query(Users).filter(Users.id == user_id).first()
        if not target_user:
            return error(
                message="User not found",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Store old status
        old_status = target_user.status

        # Update status
        target_user.status = "banned"
        target_user.updated_at = datetime.utcnow()

        # Create audit log
        admin_user_id = current_user.get("identity")
        admin_user = db.query(Users).filter(Users.id == admin_user_id).first()

        create_audit_log(
            db=db,
            user_id=admin_user_id,
            action="user.ban",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={"status": "banned", "reason": status_data.reason},
            request=request,
            username=admin_user.username if admin_user else None,
            user_email=admin_user.email if admin_user else None
        )

        db.commit()
        db.refresh(target_user)

        logger.info(f"User {user_id} banned by admin {admin_user_id}")

        response_data = UserStatusResponse(
            user_id=str(target_user.id),
            username=target_user.username,
            email=target_user.email,
            old_status=old_status,
            new_status="banned",
            changed_by=admin_user.username if admin_user else "unknown",
            reason=status_data.reason,
            changed_at=target_user.updated_at.isoformat()
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message=f"User {target_user.username} banned successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error banning user {user_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ban user"
        )


@router.post("/deactivate", response_model=DeactivateAccountResponse)
def deactivate_account(
    request: Request,
    deactivation_data: DeactivateAccountRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deactivate user's own account.

    Account will be marked as inactive and scheduled for permanent deletion after 14 days.
    User will be logged out immediately.

    - **reason**: Optional reason for deactivation
    - **confirm**: Must be true to proceed

    Returns deactivation confirmation with scheduled deletion date.
    """
    try:
        user_id = current_user.get("identity")
        logger.info(f"Account deactivation requested for user: {user_id}")

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

        # Check if already deactivated
        if db_user.status == "inactive":
            return error(
                message="Account is already deactivated",
                code=ErrorCode.INVALID_INPUT,
                status_code=400,
                severity=ErrorSeverity.LOW,
                request=request
            )

        # Update user status
        old_status = db_user.status
        db_user.status = "inactive"
        db_user.deactivated_at = datetime.utcnow()
        db_user.updated_at = datetime.utcnow()

        # Calculate scheduled deletion date (14 days from now)
        scheduled_deletion = db_user.deactivated_at + timedelta(days=14)

        # Create audit log
        create_audit_log(
            db=db,
            user_id=user_id,
            action="user.deactivate",
            resource_type="user",
            resource_id=str(user_id),
            old_values={"status": old_status},
            new_values={
                "status": "inactive",
                "deactivated_at": db_user.deactivated_at.isoformat(),
                "scheduled_deletion": scheduled_deletion.isoformat(),
                "reason": deactivation_data.reason
            },
            request=request,
            username=db_user.username,
            user_email=db_user.email
        )

        db.commit()
        db.refresh(db_user)

        logger.info(f"User {user_id} deactivated successfully. Scheduled deletion: {scheduled_deletion}")

        response_data = DeactivateAccountResponse(
            user_id=str(db_user.id),
            email=db_user.email,
            status="inactive",
            deactivated_at=db_user.deactivated_at.isoformat(),
            scheduled_deletion_at=scheduled_deletion.isoformat(),
            message=f"Account deactivated successfully. Your account will be permanently deleted on {scheduled_deletion.strftime('%B %d, %Y')}."
        )

        return success(
            data=response_data.model_dump(),
            request=request,
            message="Account deactivated successfully"
        )

    except Exception as e:
        logger.error(f"Error deactivating account for user {current_user.get('identity')}: {str(e)}")
        db.rollback()
        return error(
            message="Failed to deactivate account",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
