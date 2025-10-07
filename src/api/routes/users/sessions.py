"""User session management routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import WrextValidationException
from src.api.security.dependencies import get_current_user
from src.api.security.token_utils import verify_token
from src.services.session_service import SessionService
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler


router = APIRouter()


@router.get("/sessions")
@db_transaction_handler("list user sessions", auto_commit=False)
async def list_user_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """List all active sessions for the current user."""
    user_uuid = UUID(str(current_user.get("identity")))

    try:
        _, token = authorization.split()
    except ValueError as exc:
        raise WrextValidationException(
            message="Invalid authorization header",
            validation_errors={"authorization": "Expected 'Bearer <token>' format"}
        ) from exc

    current_payload = verify_token(token)
    current_jti = current_payload.get("jti")

    service = SessionService(db)
    sessions = await service.list_user_sessions(user_uuid)

    for session in sessions:
        session["is_current"] = session.get("token_id") == current_jti
        # Do not expose raw token identifiers
        session.pop("token_id", None)
    active_count = len(sessions)

    logger.info("Retrieved sessions for user", extra={"user_id": str(user_uuid), "count": len(sessions)})

    return {
        "sessions": sessions,
        "total_count": len(sessions),
        "active_count": active_count,
    }


@router.delete("/sessions/{session_id}")
@db_transaction_handler("revoke user session", auto_commit=True)
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """Revoke a specific user session (remote logout)."""
    user_uuid = UUID(str(current_user.get("identity")))
    service = SessionService(db)

    result = await service.revoke_session(user_uuid, UUID(str(session_id)))

    logger.info(
        "Revoked session",
        extra={"user_id": str(user_uuid), "session_id": session_id},
    )

    return {
        **result,
        "session_id": session_id,
    }


@router.delete("/sessions")
@db_transaction_handler("revoke all user sessions", auto_commit=True)
async def revoke_all_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
) -> dict:
    """Revoke all sessions except the current one."""
    user_uuid = UUID(str(current_user.get("identity")))

    try:
        _, token = authorization.split()
    except ValueError as exc:
        raise WrextValidationException(
            message="Invalid authorization header",
            validation_errors={"authorization": "Expected 'Bearer <token>' format"}
        ) from exc

    current_payload = verify_token(token)
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

    return {
        "revoked_count": revoked_count,
        "current_session_preserved": True,
    }
