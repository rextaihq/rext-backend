"""User impersonation API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import WrextValidationException
from src.api.middleware.permissions import is_admin
from src.api.schema.impersonation_schema import (
    ImpersonateStartRequest,
    ImpersonationStatusResponse,
)
from src.api.security.dependencies import get_current_user
from src.api.security.token_utils import create_access_token, create_refresh_token
from src.services.impersonation_service import ImpersonationService
from src.utils.audit_helper import create_audit_log_async
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions


router = APIRouter()


@router.post("/impersonate/start", dependencies=[Depends(is_admin)])
@require_permissions(["user.update"])
@db_transaction_handler("start impersonation", auto_commit=False)
async def start_impersonation(
    impersonate_request: ImpersonateStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Start impersonating another user and return new auth tokens."""
    admin_user_id = UUID(str(current_user.get("identity")))
    target_user_id = UUID(str(impersonate_request.user_id))

    service = ImpersonationService(db)
    impersonation_context = await service.start_impersonation(admin_user_id, target_user_id)

    access_token = create_access_token(
        {
            "identity": impersonation_context["target_user_id"],
            "username": impersonation_context["target_username"],
            "email": impersonation_context["target_email"],
            "roles": impersonation_context["roles"],
            "permissions": impersonation_context["permissions"],
            "is_impersonating": True,
            "original_user_id": str(admin_user_id),
            "impersonation_started_at": impersonation_context["impersonation_started_at"],
        }
    )
    refresh_token = create_refresh_token({"identity": impersonation_context["target_user_id"]})

    await create_audit_log_async(
        db=db,
        user_id=admin_user_id,
        action="user.impersonate.start",
        resource_type="user",
        resource_id=str(target_user_id),
        request=request,
        metadata={
            "admin_user_email": impersonation_context["impersonated_by_email"],
            "target_user_email": impersonation_context["target_email"],
            "target_user_name": impersonation_context["target_display_name"] or impersonation_context["target_username"],
        },
    )

    logger.info(
        "Impersonation started",
        extra={
            "admin_user_id": str(admin_user_id),
            "target_user_id": impersonation_context["target_user_id"],
        },
    )

    return {
        "original_user_id": str(admin_user_id),
        "impersonated_user_id": impersonation_context["target_user_id"],
        "impersonated_user_email": impersonation_context["target_email"],
        "impersonated_user_name": impersonation_context["target_display_name"] or impersonation_context["target_username"],
        "roles": impersonation_context["roles"],
        "permissions": impersonation_context["permissions"],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "started_at": impersonation_context["impersonation_started_at"],
    }


@router.post("/impersonate/stop")
@require_permissions(["user.update"])
@db_transaction_handler("stop impersonation", auto_commit=False)
async def stop_impersonation(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Stop impersonation and return tokens for the original user."""
    if not current_user.get("is_impersonating", False):
        raise WrextValidationException(
            message="Not currently impersonating",
            validation_errors={"impersonation": "You are not impersonating anyone"}
        )

    original_user_id = current_user.get("original_user_id")
    if not original_user_id:
        raise WrextValidationException(
            message="Original user ID not found in token",
            validation_errors={"token": "Invalid impersonation token"}
        )

    impersonated_user_id = current_user.get("identity")
    original_user_uuid = UUID(str(original_user_id))
    impersonated_user_uuid = UUID(str(impersonated_user_id))

    service = ImpersonationService(db)
    stop_payload = await service.stop_impersonation(original_user_uuid, impersonated_user_uuid)

    original_context = await service.get_user_context(original_user_uuid)

    access_token = create_access_token(
        {
            "identity": original_context["user_id"],
            "username": original_context["username"],
            "email": original_context["email"],
            "roles": original_context["roles"],
            "permissions": original_context["permissions"],
            "is_impersonating": False,
        }
    )
    refresh_token = create_refresh_token({"identity": original_context["user_id"]})

    await create_audit_log_async(
        db=db,
        user_id=original_user_uuid,
        action="user.impersonate.stop",
        resource_type="user",
        resource_id=str(impersonated_user_id),
        request=request,
        metadata={
            "original_user_email": original_context["email"],
            "impersonated_user_id": str(impersonated_user_id),
        },
    )

    logger.info(
        "Impersonation stopped",
        extra={
            "original_user_id": original_context["user_id"],
            "impersonated_user_id": str(impersonated_user_uuid),
        },
    )

    return {
        "message": "Impersonation stopped",
        "admin_user_id": original_context["user_id"],
        "impersonation_stopped_at": stop_payload["impersonation_stopped_at"],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "roles": original_context["roles"],
        "permissions": original_context["permissions"],
    }


@router.get("/impersonate/status", response_model=ImpersonationStatusResponse)
@require_permissions(["user.read"])
async def get_impersonation_status(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Get the current impersonation status.
    
    Returns impersonation details if the current user is impersonating someone,
    or a simple status response if not impersonating.
    
    This endpoint reads from the JWT token and does not require database access.
    """
    is_impersonating = current_user.get("is_impersonating", False)
    
    if not is_impersonating:
        return {"is_impersonating": False}
    
    # Build response with impersonation details from JWT token
    response = {
        "is_impersonating": True,
        "original_user_id": current_user.get("original_user_id"),
        "impersonated_user_id": current_user.get("identity"),
        "impersonated_user_email": current_user.get("email"),
        "impersonated_user_name": current_user.get("username"),
        "started_at": current_user.get("impersonation_started_at"),
    }
    
    logger.debug(
        "Impersonation status checked",
        extra={
            "is_impersonating": is_impersonating,
            "impersonated_user_id": response.get("impersonated_user_id"),
        },
    )
    
    return response
