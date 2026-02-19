"""User impersonation API routes."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextValidationException
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
@require_permissions("user.update", workspace_scoped=False)
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
    
    # Generate unique session ID
    session_id = str(uuid4())

    
    

    service = ImpersonationService(db)
    impersonation_context = await service.start_impersonation(admin_user_id, target_user_id)

    access_token = create_access_token(
        {
            "id": impersonation_context["target_user_id"],
            "full_name": impersonation_context["target_full_name"],
            "email": impersonation_context["target_email"],
            "roles": impersonation_context["roles"],
            "permissions": impersonation_context["permissions"],
            "is_impersonating": True,
            "original_user_id": str(admin_user_id),
            "impersonation_started_at": impersonation_context["impersonation_started_at"],
            "session_id": session_id
        }
    )
    refresh_token = create_refresh_token({
    "id": impersonation_context["target_user_id"],
    "session_id": session_id
})

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
            "target_user_name": (
                impersonation_context["target_display_name"]
                or impersonation_context["target_full_name"]
            ),
            "session_id": session_id
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
        "impersonated_user_name": (
            impersonation_context["target_display_name"]
            or impersonation_context["target_full_name"]
        ),
        "roles": impersonation_context["roles"],
        "permissions": impersonation_context["permissions"],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "started_at": impersonation_context["impersonation_started_at"],
        "session_id": session_id
    }
@router.post("/impersonate/stop")
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("stop impersonation", auto_commit=True) 
async def stop_impersonation(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Stop impersonation and return tokens for the original user."""
    
    # Use RextValidationException without validation_errors
    if not current_user.get("is_impersonating", False):
        raise RextValidationException(
            message="Not currently impersonating"
        )

    original_user_id = current_user.get("original_user_id")
    if not original_user_id:
        raise RextValidationException(
            message="Original user ID not found in token"
        )
    
    session_id = current_user.get("session_id")
    if not session_id:
        raise RextValidationException(
            message="Session ID not found in token"
        )

    impersonated_user_id = current_user.get("identity")
    original_user_uuid = UUID(str(original_user_id))
    impersonated_user_uuid = UUID(str(impersonated_user_id))

    service = ImpersonationService(db)
    
    # Invalidate the impersonation session
    await service.invalidate_session(session_id)
    
    # Stop impersonation in service layer
    stop_payload = await service.stop_impersonation(original_user_uuid, impersonated_user_uuid)

    original_context = await service.get_user_context(original_user_uuid)

    access_token = create_access_token(
        {
            "id": original_context["user_id"],
            "full_name": original_context["full_name"],
            "email": original_context["email"],
            "roles": original_context["roles"],
            "permissions": original_context["permissions"],
            "is_impersonating": False,
        }
    )
    refresh_token = create_refresh_token({"id": original_context["user_id"]})

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
            "session_id": session_id,
        },
    )

    logger.info(
        "Impersonation stopped and session invalidated",
        extra={
            "original_user_id": original_context["user_id"],
            "impersonated_user_id": str(impersonated_user_uuid),
            "session_id": session_id,
        },
    )

    return {
        "message": "Impersonation stopped successfully",
        "admin_user_id": original_context["user_id"],
        "impersonation_stopped_at": stop_payload["impersonation_stopped_at"],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "roles": original_context["roles"],
        "permissions": original_context["permissions"],
    }

@router.get("/impersonate/status", response_model=ImpersonationStatusResponse)
@require_permissions("user.read", workspace_scoped=False)
async def get_impersonation_status(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Get the current impersonation status.

    Return impersonation details if the current user is impersonating someone,
    or a simple status response if not impersonating.

    Requires user.read permission for consistency with other user-related endpoints.
    """
    is_impersonating = current_user.get("is_impersonating", False)
    session_id = current_user.get("session_id")
    
    if is_impersonating and session_id:
        service = ImpersonationService(db)
        is_valid = await service.is_session_valid(session_id)
        
        if not is_valid:
            raise HTTPException(
        status_code=401,  
        detail="Impersonation session has been invalidated. Please obtain a new token.",
    )
    
    if not is_impersonating:
        return {"is_impersonating": False}
    
    # Build response with impersonation details from JWT token
    response = {
        "is_impersonating": True,
        "original_user_id": current_user.get("original_user_id"),
        "impersonated_user_id": current_user.get("identity"),
        "impersonated_user_email": current_user.get("email"),
        "impersonated_user_name": current_user.get("full_name"),
        "started_at": current_user.get("impersonation_started_at"),
        "session_id": session_id
    }
    
    logger.debug(
        "Impersonation status checked",
        extra={
            "is_impersonating": is_impersonating,
            "impersonated_user_id": response.get("impersonated_user_id"),
            "session_id": session_id
        },
    )
    
    return response
