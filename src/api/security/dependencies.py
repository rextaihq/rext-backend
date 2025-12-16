"""
FastAPI authentication dependencies.

This module contains FastAPI dependency functions for authentication,
separated from core auth logic to avoid circular imports.
"""

from typing import TYPE_CHECKING
from fastapi import Header, Depends, HTTPException, Query
from langgraph_sdk import Auth
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.token_utils import verify_token, is_token_blacklisted
from src.utils.logger import logger

# Lazy import to avoid circular dependency
if TYPE_CHECKING:
    from src.api.middleware.exceptions import (
        WrextAuthenticationException,
        TokenExpiredException,
    )


async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_async_db)
) -> Auth.types.MinimalUserDict:
    """Check if the user's token is valid and not blacklisted."""
    # Import exceptions at runtime to avoid circular dependency
    from src.api.middleware.exceptions import (
        WrextAuthenticationException,
        TokenExpiredException,
    )

    if not authorization:
        raise WrextAuthenticationException(
            message="Authorization header missing",
            context={"expected_format": "Bearer <token>"}
        )
    try:
        scheme, token = authorization.split()
    except ValueError:
        raise WrextAuthenticationException(
            message="Invalid authorization header format",
            context={"expected_format": "Bearer <token>"}
        )

    if scheme.lower() != "bearer":
        raise WrextAuthenticationException(
            message="Invalid authentication scheme",
            context={"provided_scheme": scheme, "expected_scheme": "bearer"}
        )

    try:
        # Verify the token
        payload = verify_token(token)

        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti and await is_token_blacklisted(jti, db):
            raise WrextAuthenticationException(
                message="Token has been revoked",
                context={"reason": "Token blacklisted"}
            )

    except HTTPException as e:
        if "expired" in str(e.detail).lower():
            raise TokenExpiredException(
                message="Authentication token has expired"
            )
        else:
            raise WrextAuthenticationException(
                message="Invalid authentication token",
                context={"token_error": str(e.detail)}
            )
    except WrextAuthenticationException:
        # Re-raise authentication exceptions (including blacklist check)
        raise
    except Exception as e:
        raise WrextAuthenticationException(
            message="Token validation failed",
            context={"error_details": str(e)}
        )

    # Extract user info from JWT payload
    user_id = payload.get("id")  # usually `sub` holds user id
    if not user_id:
        raise WrextAuthenticationException(
            message="User ID missing in token payload",
            context={"payload_keys": list(payload.keys())}
        )

    user_info = {
        "identity": user_id,
        "username": payload.get("username"),
        "email": payload.get("email"),
        "roles": payload.get("roles", []),
        "is_impersonating": payload.get("is_impersonating", False),
        "original_user_id": payload.get("original_user_id"),
        "impersonation_started_at": payload.get("impersonation_started_at"),
    }

    # Log identity verification without PII
    logger.info("Identity verified", extra={"user_id": user_id})
    return user_info


async def get_current_user_optional(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_async_db)
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
    token: str = Query(None),
    db: AsyncSession = Depends(get_async_db)
) -> Auth.types.MinimalUserDict:
    """
    Authentication dependency for SSE that supports both Header and Query param.
    EventSource API does not support custom headers, so we allow passing token via query param.
    """
    # Import exceptions at runtime to avoid circular dependency
    from src.api.middleware.exceptions import (
        WrextAuthenticationException,
        TokenExpiredException,
    )

    auth_token = None
    if authorization:
        try:
            scheme, param = authorization.split()
            if scheme.lower() == "bearer":
                auth_token = param
        except ValueError:
            pass
    
    if not auth_token and token:
        auth_token = token

    if not auth_token:
        raise WrextAuthenticationException(
            message="Authentication required",
            context={"expected_sources": ["Authorization header", "token query param"]}
        )

    try:
        # Verify the token
        payload = verify_token(auth_token)

        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti and await is_token_blacklisted(jti, db):
            raise WrextAuthenticationException(
                message="Token has been revoked",
                context={"reason": "Token blacklisted"}
            )

    except HTTPException as e:
        if "expired" in str(e.detail).lower():
            raise TokenExpiredException(
                message="Authentication token has expired"
            )
        else:
            raise WrextAuthenticationException(
                message="Invalid authentication token",
                context={"token_error": str(e.detail)}
            )
    except WrextAuthenticationException:
        raise
    except Exception as e:
        raise WrextAuthenticationException(
            message="Token validation failed",
            context={"error_details": str(e)}
        )

    # Extract user info from JWT payload
    user_id = payload.get("id")
    if not user_id:
        raise WrextAuthenticationException(
            message="User ID missing in token payload",
            context={"payload_keys": list(payload.keys())}
        )

    user_info = {
        "identity": user_id,
        "username": payload.get("username"),
        "email": payload.get("email"),
        "roles": payload.get("roles", []),
        "is_impersonating": payload.get("is_impersonating", False),
        "original_user_id": payload.get("original_user_id"),
        "impersonation_started_at": payload.get("impersonation_started_at"),
    }

    # Log identity verification without PII
    logger.info("Identity verified for SSE", extra={"user_id": user_id})
    return user_info