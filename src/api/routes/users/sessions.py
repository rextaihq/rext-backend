from fastapi import APIRouter, Depends, Request, Header
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user
from src.api.schema.session_schema import SessionResponse
from src.api.security.token_utils import verify_token
from sqlalchemy.orm import Session
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.database.database import get_db
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import WrextValidationException
from datetime import datetime

router = APIRouter()


@router.get("/sessions")
def list_user_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    List all active sessions for the current user.

    Shows sessions across all devices with device info, IP addresses,
    and activity timestamps. Marks the current session for UI display.

    Args:
        request: FastAPI request object
        current_user: Current authenticated user
        authorization: Authorization header with current token
        db: Database session

    Returns:
        List of user sessions with metadata
    """
    try:
        user_id = current_user.get("identity")

        # Get current token's JTI to mark current session
        scheme, token = authorization.split()
        current_payload = verify_token(token)
        current_jti = current_payload.get("jti")

        # Query all active sessions for user
        sessions = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        ).order_by(UserSession.last_activity_at.desc()).all()

        # Convert to response format
        session_list = []
        for session in sessions:
            session_dict = session.to_dict()
            session_dict["is_current"] = (session.jti == current_jti)
            session_list.append(SessionResponse(**session_dict))

        logger.info(f"Retrieved {len(session_list)} active sessions for user {user_id}")

        return success(
            data={
                "sessions": [s.model_dump() for s in session_list],
                "total_count": len(session_list),
                "active_count": len([s for s in session_list if s.is_active])
            },
            request=request,
            message="Sessions retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Failed to list sessions: {str(e)}")
        return error(
            message="Failed to retrieve sessions",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revoke a specific user session (remote logout).

    Deactivates the session and blacklists the associated token.
    The user will be logged out on that device on next API call.

    Args:
        session_id: UUID of the session to revoke
        request: FastAPI request object
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success confirmation

    Raises:
        404: If session not found or doesn't belong to user
    """
    try:
        user_id = current_user.get("identity")

        # Find session
        session = db.query(UserSession).filter(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.is_active == True
        ).first()

        if not session:
            raise WrextValidationException(
                message="Session not found or already revoked",
                context={"session_id": session_id}
            )

        # Blacklist the token
        blacklist_entry = TokenBlacklist(
            jti=session.jti,
            token_type="access",
            user_id=user_id,
            revoked_at=datetime.utcnow(),
            expires_at=session.expires_at,
            reason="session_revoked"
        )
        db.add(blacklist_entry)

        # Deactivate session
        session.is_active = False
        session.revoked_at = datetime.utcnow()
        db.commit()

        logger.info(f"Revoked session {session_id} for user {user_id}")

        return success(
            data={"session_id": session_id, "revoked": True},
            request=request,
            message="Session revoked successfully"
        )

    except WrextValidationException:
        raise
    except Exception as e:
        logger.error(f"Failed to revoke session: {str(e)}")
        return error(
            message="Failed to revoke session",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.delete("/sessions")
def revoke_all_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """
    Revoke all sessions except the current one (logout all other devices).

    Useful for security purposes when user suspects unauthorized access.
    Blacklists all tokens and deactivates all sessions except current.

    Args:
        request: FastAPI request object
        current_user: Current authenticated user
        authorization: Authorization header with current token
        db: Database session

    Returns:
        Count of revoked sessions
    """
    try:
        user_id = current_user.get("identity")

        # Get current token's JTI to preserve current session
        scheme, token = authorization.split()
        current_payload = verify_token(token)
        current_jti = current_payload.get("jti")

        # Find all other active sessions
        other_sessions = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_active == True,
            UserSession.jti != current_jti
        ).all()

        revoked_count = 0
        for session in other_sessions:
            # Blacklist token
            blacklist_entry = TokenBlacklist(
                jti=session.jti,
                token_type="access",
                user_id=user_id,
                revoked_at=datetime.utcnow(),
                expires_at=session.expires_at,
                reason="all_sessions_revoked"
            )
            db.add(blacklist_entry)

            # Deactivate session
            session.is_active = False
            session.revoked_at = datetime.utcnow()
            revoked_count += 1

        db.commit()

        logger.info(f"Revoked {revoked_count} sessions for user {user_id} (kept current)")

        return success(
            data={"revoked_count": revoked_count, "current_session_preserved": True},
            request=request,
            message=f"Revoked {revoked_count} sessions successfully"
        )

    except Exception as e:
        logger.error(f"Failed to revoke all sessions: {str(e)}")
        return error(
            message="Failed to revoke sessions",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )
