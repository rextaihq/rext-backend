"""
FastAPI authentication dependencies.

This module contains FastAPI dependency functions for authentication,
separated from core auth logic to avoid circular imports.
"""

from uuid import UUID

from fastapi import Depends, Header, HTTPException
from langgraph_sdk import Auth
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db

# Lazy import to avoid circular dependency
# if TYPE_CHECKING:
from src.api.middleware.exceptions import (
    DatabaseConnectionException,
    RextAuthenticationException,
    TokenExpiredException,
)
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.user_models.users import Users
from src.api.schema.response_schemas import ErrorCode
from src.api.security.token_utils import decode_and_verify_token, is_token_blacklisted
from src.utils.logger import logger

# Account statuses that must reject an already-issued access token, with the
# error code the frontend uses to sign the tab out and explain why.
_BLOCKED_STATUSES = {
    "suspended": (
        ErrorCode.ACCOUNT_SUSPENDED,
        "Your account has been suspended. Please contact support for assistance.",
    ),
    "banned": (
        ErrorCode.ACCOUNT_BANNED,
        "Your account has been banned. Please contact support for assistance.",
    ),
}


def _session_check_could_not_run(error: Exception, where: str) -> DatabaseConnectionException:
    """The answer when a session check could not read the database: 503, never a 401
    (rext-control#874).

    The token's blacklist row and the session's row are read on every request. When those reads
    fail, the caller's token has not been found wanting: the server could not look. Answered as
    401 "Token validation failed", it told a signed-in person their sign-in was bad (seen on
    staging on 8 October 2026, in a stopping process's last seconds). A 503 says what happened:
    try again. The log names the error's type and where; the caller is told neither.

    Which errors: every one the reads raise once the token has decoded, unless it is an
    authentication verdict. Not a list of database error types: a stopping process fails these
    reads with whatever its closing event loop raises, and none of it is about the token.
    """
    logger.error(
        "Session check could not read the database in %s (%s): answering 503",
        where,
        type(error).__name__,
        exc_info=True,
    )
    return DatabaseConnectionException(
        message="We could not check your session just now. Please try again.",
        context={"during": where},
    )


async def _say_which_session_was_refused(db: AsyncSession, session_id: UUID, user_id: UUID) -> None:
    """One log line for a session the check refuses (rext-control#858): which one, and what a
    second read of its row says.

    Sessions that existed and were active have been refused in the seconds after their sign-in
    and accepted again a moment later, and the log could not say which session a refused
    request spoke for. The last characters of the two ids match a refusal to its sign-in
    ("User logged in" carries the session id), and the second read tells a session that was
    really ended from a read that missed its row. Never raises: the request is refused either way.
    """
    try:
        row = (
            await db.execute(
                select(
                    UserSession.is_active,
                    UserSession.revoked_at,
                    UserSession.user_id,
                    func.extract("epoch", func.now() - UserSession.created_at),
                    func.pg_backend_pid(),
                ).where(UserSession.id == session_id)
            )
        ).first()
        if row is None:
            found = "no row with that id"
        else:
            active, revoked_at, owner, age, backend = row
            state = "active" if active else ("revoked" if revoked_at else "inactive")
            whose = "this user's" if owner == user_id else "another user's"
            found = (
                f"a row that is {state}, {whose}, made {float(age):.1f} s ago (backend {backend})"
            )
    except Exception as exc:  # noqa: BLE001 - a diagnostic must not change the answer
        found = f"it could not be read ({type(exc).__name__})"
    logger.warning(
        "Session refused: session ..%s of user ..%s; read again: %s",
        str(session_id)[-4:],
        str(user_id)[-4:],
        found,
    )


async def _ensure_impersonation_may_go_on(payload: dict, db: AsyncSession) -> None:
    """Refuse an impersonated session that could no longer be started.

    The session is the admin's who started it. It ends when it is stopped, when that
    account is suspended, banned or deleted, when it no longer holds user.impersonate,
    and when it no longer outranks the account it acts as: on the next request, not
    when the token runs out.
    """
    # Imported here: loading the services reaches back into this module for
    # get_current_user (src.api.middleware.permissions).
    from src.services.impersonation_service import ImpersonationService

    try:
        admin_id = UUID(str(payload.get("original_user_id")))
        target_id = UUID(str(payload.get("id")))
    except (TypeError, ValueError) as exc:
        raise RextAuthenticationException(message="Authentication session is invalid") from exc

    status = (
        await db.execute(select(Users.status).where(Users.id == admin_id))
    ).scalar_one_or_none()
    still_allowed = (
        status is not None
        and status not in _BLOCKED_STATUSES
        and await ImpersonationService(db).may_go_on(admin_id, target_id, payload.get("session_id"))
    )
    if not still_allowed:
        raise RextAuthenticationException(message="This impersonation session has ended")


async def _ensure_active_user_session(payload: dict, db: AsyncSession) -> None:
    """Reject already-issued access tokens whose user or session is no longer usable.

    Runs on every authenticated request (both get_current_user and the SSE
    variant), so an admin suspending or banning a user takes effect on their
    next call instead of only at the next login.
    """
    try:
        user_id = UUID(str(payload.get("id")))
    except (TypeError, ValueError) as exc:
        raise RextAuthenticationException(message="Authentication session is invalid") from exc

    status = (
        await db.execute(select(Users.status).where(Users.id == user_id))
    ).scalar_one_or_none()
    blocked = _BLOCKED_STATUSES.get(status)
    if blocked:
        error_code, message = blocked
        raise RextAuthenticationException(
            message=message,
            error_code=error_code,
            context={"status": status},
        )

    if payload.get("is_impersonating") or payload.get("session_kind") == "impersonation":
        await _ensure_impersonation_may_go_on(payload, db)

    if payload.get("session_kind") != "user":
        return
    try:
        session_id = UUID(str(payload.get("session_id")))
    except (TypeError, ValueError) as exc:
        raise RextAuthenticationException(message="Authentication session is invalid") from exc

    result = await db.execute(
        select(UserSession.id).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.is_active.is_(True),
        )
    )
    if result.scalar_one_or_none() is None:
        await _say_which_session_was_refused(db, session_id, user_id)
        raise RextAuthenticationException(message="Authentication session has been revoked")


async def get_current_user(
    authorization: str = Header(...), db: AsyncSession = Depends(get_async_db)
) -> Auth.types.MinimalUserDict:
    """Check if the user's token is valid and not blacklisted."""
    # Import exceptions at runtime to avoid circular dependency
    from src.api.middleware.exceptions import (
        RextAuthenticationException,
    )

    if not authorization:
        raise RextAuthenticationException(
            message="Authorization header missing", context={"expected_format": "Bearer <token>"}
        )
    try:
        scheme, token = authorization.split()
    except ValueError:
        raise RextAuthenticationException(
            message="Invalid authorization header format",
            context={"expected_format": "Bearer <token>"},
        )

    if scheme.lower() != "bearer":
        raise RextAuthenticationException(
            message="Invalid authentication scheme",
            context={"provided_scheme": scheme, "expected_scheme": "bearer"},
        )

    payload = None
    try:
        # Verify the token
        payload = decode_and_verify_token(token)

        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti and await is_token_blacklisted(jti, db):
            raise RextAuthenticationException(
                message="Token has been revoked", context={"reason": "Token blacklisted"}
            )
        await _ensure_active_user_session(payload, db)

    except HTTPException as e:
        if "expired" in str(e.detail).lower():
            raise TokenExpiredException(message="Authentication token has expired")
        else:
            raise RextAuthenticationException(
                message="Invalid authentication token", context={"token_error": str(e.detail)}
            )
    except RextAuthenticationException:
        # Re-raise authentication exceptions (including blacklist check)
        raise
    except Exception as e:
        if payload is not None:
            # The token decoded: what failed is the server's own read, not the token.
            raise _session_check_could_not_run(e, "get_current_user") from e
        logger.error(f"Unexpected error in get_current_user: {str(e)}", exc_info=True)
        raise RextAuthenticationException(
            message="Token validation failed",
            context={"error_details": "get_current_user", "original_error": str(e)},
        )

    # Extract user info from JWT payload
    user_id = payload.get("id")  # usually `sub` holds user id
    if not user_id:
        raise RextAuthenticationException(
            message="User ID missing in token payload",
            context={"payload_keys": list(payload.keys())},
        )

    user_info = {
        "identity": user_id,
        "email": payload.get("email"),
        "roles": payload.get("roles", []),
        "is_impersonating": payload.get("is_impersonating", False),
        "original_user_id": payload.get("original_user_id"),
        "impersonation_started_at": payload.get("impersonation_started_at"),
        "session_id": payload.get("session_id"),
        "session_kind": payload.get("session_kind"),
    }

    # Log identity verification without PII
    logger.info("Identity verified", extra={"user_id": user_id})
    return user_info


async def get_current_active_user(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> Users:
    """Return current authenticated user row and enforce soft-delete check."""
    user_id = current_user.get("identity")
    if not user_id:
        from src.api.middleware.exceptions import RextAuthenticationException

        raise RextAuthenticationException(
            message="User ID missing in token payload",
            context={"source": "get_current_active_user"},
        )
    result = await db.execute(
        select(Users).where(Users.id == UUID(str(user_id)), Users.deleted_at.is_(None))
    )
    db_user = result.scalar_one_or_none()
    if not db_user:
        from src.api.middleware.exceptions import RextAuthenticationException

        raise RextAuthenticationException(
            message="User not found or has been deleted",
            context={"user_id": str(user_id)},
        )
    return db_user


async def get_current_user_optional(
    authorization: str = Header(None), db: AsyncSession = Depends(get_async_db)
) -> Auth.types.MinimalUserDict | None:
    """
    Optional authentication dependency.
    Returns user info if valid token provided, None otherwise.
    Does not raise exceptions for missing/invalid auth.
    """
    if not authorization:
        return None

    try:
        return await get_current_user(authorization, db)
    except Exception:
        # Silently return None for any authentication errors
        return None


async def get_current_user_sse(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_async_db),
) -> Auth.types.MinimalUserDict:
    """
    Authentication dependency for the SSE streams: the Authorization header only.

    The dashboard streams with fetch-event-source, which sends headers. The old
    `?token=` query parameter is gone: a token in a URL ends up in access logs.
    """
    # Import exceptions at runtime to avoid circular dependency
    from src.api.middleware.exceptions import (
        RextAuthenticationException,
    )

    auth_token = None
    if authorization:
        try:
            scheme, param = authorization.split()
            if scheme.lower() == "bearer":
                auth_token = param
        except ValueError:
            pass

    if not auth_token:
        raise RextAuthenticationException(
            message="Authentication required",
            context={"expected_sources": ["Authorization header"]},
        )

    payload = None
    try:
        # Verify the token
        payload = decode_and_verify_token(auth_token)

        # A stream keeps this request's session for its whole life: the two reads below must
        # not leave their transaction open, or every live stream holds a database connection
        # idle in transaction until it closes (G79, rext-control#643). Both are read-only.
        try:
            # Check if token is blacklisted
            jti = payload.get("jti")
            if jti and await is_token_blacklisted(jti, db):
                raise RextAuthenticationException(
                    message="Token has been revoked", context={"reason": "Token blacklisted"}
                )
            await _ensure_active_user_session(payload, db)
        finally:
            await db.rollback()

    except HTTPException as e:
        if "expired" in str(e.detail).lower():
            raise TokenExpiredException(message="Authentication token has expired")
        else:
            raise RextAuthenticationException(
                message="Invalid authentication token",
                context={"token_error": "get_current_user_optional"},
            )
    except RextAuthenticationException:
        # Re-raise authentication exceptions (including blacklist check)
        raise
    except Exception as e:
        if payload is not None:
            # The token decoded: what failed is the server's own read, not the token.
            raise _session_check_could_not_run(e, "get_current_user_sse") from e
        logger.error(f"Unexpected error in get_current_user_sse: {str(e)}", exc_info=True)
        raise RextAuthenticationException(
            message="Token validation failed",
            context={"error_details": "Token validation failed", "original_error": str(e)},
        )

    # Extract user info from JWT payload
    user_id = payload.get("id")
    if not user_id:
        raise RextAuthenticationException(
            message="User ID missing in token payload",
            context={"payload_keys": list(payload.keys())},
        )

    user_info = {
        "identity": user_id,
        "email": payload.get("email"),
        "roles": payload.get("roles", []),
        "is_impersonating": payload.get("is_impersonating", False),
        "original_user_id": payload.get("original_user_id"),
        "impersonation_started_at": payload.get("impersonation_started_at"),
        "session_id": payload.get("session_id"),
        "session_kind": payload.get("session_kind"),
    }

    # Log identity verification without PII
    logger.info("Identity verified for SSE", extra={"user_id": user_id})
    return user_info
