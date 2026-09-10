"""User session management routes.

Note: The POST /sessions/revoke-all endpoint is deprecated.
It was added for frontend compatibility but DELETE /sessions
should be used for new integrations. The POST endpoint is
scheduled for removal after the frontend is migrated.

See: [Frontend Migration Ticket URL]
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextValidationException
from src.api.schema.response.session_responses import (
    BulkSessionRevokeResponse,
    SessionListResponse,
    SessionRevokeResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.api.security.token_utils import decode_and_verify_token
from src.services.session_service import SessionService
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter()


@router.get("/sessions", response_model=SuccessResponse[SessionListResponse])
@require_permissions("user.read", workspace_scoped=False)
@db_transaction_handler("list user sessions", auto_commit=False)
async def list_user_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db),
):
    """List all active sessions for the current user."""
    user_uuid = UUID(str(current_user.get("identity")))

    try:
        _, token = authorization.split()
    except ValueError as exc:
        raise RextValidationException(
            message="Invalid authorization header",
            validation_errors={"authorization": "Expected 'Bearer <token>' format"},
        ) from exc

    current_payload = decode_and_verify_token(token)
    current_jti = current_payload.get("jti")

    service = SessionService(db)
    sessions = await service.list_user_sessions(user_uuid)

    for session in sessions:
        session["is_current"] = session.get("token_id") == current_jti
        # Do not expose raw token identifiers
        session.pop("token_id", None)
    active_count = len(sessions)

    logger.info(
        "Retrieved sessions for user", extra={"user_id": str(user_uuid), "count": len(sessions)}
    )

    return success(
        data={
            "sessions": sessions,
            "total_count": len(sessions),
            "active_count": active_count,
        },
        request=request,
        message="User sessions retrieved successfully",
    )


@router.delete("/sessions/{session_id}", response_model=SuccessResponse[SessionRevokeResponse])
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("revoke user session", auto_commit=True)
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Revoke a specific user session (remote logout)."""
    user_uuid = UUID(str(current_user.get("identity")))
    service = SessionService(db)

    result = await service.revoke_session(user_uuid, UUID(str(session_id)))

    logger.info(
        "Revoked session",
        extra={"user_id": str(user_uuid), "session_id": session_id},
    )

    return success(
        data={
            **result,
            "session_id": session_id,
        },
        request=request,
        message="Session revoked successfully",
    )


@router.delete("/sessions", response_model=SuccessResponse[BulkSessionRevokeResponse])
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("revoke all user sessions", auto_commit=True)
async def revoke_all_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db),
):
    """Revoke all sessions except the current one."""
    user_uuid = UUID(str(current_user.get("identity")))

    try:
        _, token = authorization.split()
    except ValueError as exc:
        raise RextValidationException(
            message="Invalid authorization header",
            validation_errors={"authorization": "Expected 'Bearer <token>' format"},
        ) from exc

    current_payload = decode_and_verify_token(token)
    current_jti = current_payload.get("jti")

    service = SessionService(db)
    exclude_session_id = None
    if current_payload.get("session_id"):
        try:
            exclude_session_id = UUID(str(current_payload.get("session_id")))
        except (ValueError, TypeError):
            exclude_session_id = None

    revoked_count = await service.revoke_all_sessions(
        user_uuid,
        exclude_session_id=exclude_session_id,
        exclude_session_jti=current_jti,
    )

    logger.info(
        "Revoked other sessions",
        extra={"user_id": str(user_uuid), "revoked_count": revoked_count},
    )

    return success(
        data={
            "revoked_count": revoked_count,
            "current_session_preserved": True,
        },
        request=request,
        message="All other sessions revoked successfully",
    )


@router.post(
    "/sessions/revoke-all",
    deprecated=True,
    response_model=SuccessResponse[BulkSessionRevokeResponse],
)
@require_permissions("user.update", workspace_scoped=False)
@db_transaction_handler("revoke all user sessions (POST)", auto_commit=True)
async def revoke_all_sessions_post(
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Revoke all sessions except the current one.

    .. deprecated::
        This endpoint is deprecated. Use DELETE /sessions instead.
        This endpoint exists for legacy frontend compatibility and will be
        removed in a future version.
    """
    # Add deprecation header for API consumers
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"  # Plan removal date
    response.headers["Link"] = '</api/user/sessions>; rel="successor-version"'

    # Log deprecation warning for monitoring
    logger.warning(
        "Deprecated endpoint called: POST /sessions/revoke-all",
        extra={
            "user_id": str(current_user.get("identity")),
            "deprecated_endpoint": "POST /sessions/revoke-all",
            "replacement_endpoint": "DELETE /sessions",
        },
    )

    # Reuse the same logic as DELETE /sessions
    # This returns the JSONResponse from success()
    return await revoke_all_sessions(request, current_user, authorization, db)
