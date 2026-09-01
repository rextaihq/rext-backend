"""
JWT Token Utilities

Provides functions for creating and verifying JWT tokens for authentication.

Security Features:
- Cryptographic signing using PyJWT[crypto] with support for:
  * HMAC algorithms: HS256, HS384, HS512 (symmetric)
  * RSA algorithms: RS256, RS384, RS512 (asymmetric)
  * EC algorithms: ES256, ES384, ES512 (elliptic curve)
- Token blacklisting support via JTI (JWT ID)
- Configurable token expiration
- Separate secrets for access and refresh tokens

Default Configuration:
- Algorithm: HS256 (HMAC-SHA256)
- Access Token Expiration: 30 minutes (configurable)
- Refresh Token Expiration: 7 days (configurable)

Note: While multiple algorithms are available, we use HS256 (HMAC) by default
for simplicity. For higher security requirements, consider using RS256 (RSA)
or ES256 (Elliptic Curve) with asymmetric key pairs.
"""

import uuid
import warnings
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from src.api.config import get_settings
from src.utils.logger import logger

# Load settings (validated on application startup)
# Settings are loaded from environment variables and validated using Pydantic
_settings = get_settings()
SECRET_KEY = _settings.SECRET_KEY
ALGORITHM = _settings.ALGORITHM
REFRESH_SECRET_KEY = _settings.REFRESH_SECRET_KEY

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")
# Encrypt Password
def hash_password(password: str) -> str:
    """
    Hashes a plain text password using bcrypt.

    Args:
        password (str): The plain text password.

    Returns:
        str: The hashed password.
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# verify password
def verify_password(password: str, hashed_password: str | None) -> bool:
    """
    Verifies that a plain text password matches the hashed password.

    Args:
        password (str): The plain text password.
        hashed_password (str | None): The hashed password from the database.

    Returns:
        bool: True if the password matches, False otherwise.
    """
    if hashed_password is None or hashed_password == "oauth_no_password":
        return False
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# Create Access Token
def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Creates a JWT access token with JTI for blacklisting support.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to configured value.

    Returns:
        str: The JWT token.
    """
    to_encode = data.copy()
    if expires_delta is None:
        expires_delta = timedelta(minutes=_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    jti = str(uuid.uuid4())  # Unique token ID for blacklisting
    to_encode.update({
        "exp": expire,
        "jti": jti,
        "type": "access"
    })
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

# Refresh token
def create_refresh_token(
    data: dict,
    expires_delta: timedelta = None,
    *,
    jti: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> str:
    """
    Creates a long-lived refresh token with JTI for blacklisting support.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token lifetime. Defaults to the
            configured value.
        jti (str, optional): Explicit token ID. Rotation uses this to recreate
            the same successor after a concurrent request or process restart.
        expires_at (datetime, optional): Explicit expiration instant. Mutually
            exclusive with ``expires_delta``.

    Returns:
        str: The JWT refresh token.
    """
    if expires_delta is not None and expires_at is not None:
        raise ValueError("expires_delta and expires_at are mutually exclusive")

    to_encode = data.copy()
    if expires_at is None:
        if expires_delta is None:
            expires_delta = timedelta(days=_settings.REFRESH_TOKEN_EXPIRE_DAYS)
        expires_at = datetime.now(timezone.utc) + expires_delta

    # NumericDate values are deliberately integers. This makes a reconstructed
    # refresh token byte-for-byte stable across workers and process restarts.
    expire = int(expires_at.timestamp())
    token_jti = jti or str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "jti": token_jti,
        "type": "refresh"
    })
    return jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)


# Reset Token
def create_reset_token(data: dict, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    """
    Creates a JWT token for password reset with JTI and type.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to 30 minutes.

    Returns:
        str: The JWT token.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "jti": jti,
        "type": "password_reset"
    })
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

# Verification Token
def create_verification_token(data: dict, expires_delta: timedelta = timedelta(hours=24)) -> str:
    """
    Creates a JWT token for email verification with JTI and type.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to 24 hours.

    Returns:
        str: The JWT token.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "jti": jti,
        "type": "email_verification"
    })
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

# Account Recovery Token
def create_recovery_token(data: dict, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    """
    Creates a JWT token for account recovery with JTI and type.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to 30 minutes.

    Returns:
        str: The JWT token.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "jti": jti,
        "type": "account_recovery"
    })
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

# def verify_reset_token(token: str) -> dict | None:
#     """
#     Verify and decode the JWT reset token.

#     Args:
#         token (str): The JWT reset token.

#     Returns:
#         dict | None: The decoded payload if valid, else None.
#     """
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         return payload
#     except Exception:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid or expired reset token",
#             headers={"WWW-Authenticate": "Bearer"},
#         )


def decode_and_verify_token(token: str, expected_type: str | None = None) -> dict:
    """
    Decode and verify a JWT token.

    This is a pure utility function for direct calls. For FastAPI route
    dependencies, use the VerifiedToken annotated type instead.

    Args:
        token: The JWT token string to verify.

    Returns:
        dict: The decoded token payload.

    Raises:
        HTTPException: If token is invalid, expired, or malformed.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check token type if expected
        if expected_type and payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type - expected {expected_type}",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )


def _get_verified_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency that extracts and verifies the JWT token from the
    Authorization header.

    This is an internal function. Use VerifiedToken type annotation in routes.
    """
    return decode_and_verify_token(token)


# Type alias for use in route function signatures
VerifiedToken = Annotated[dict, Depends(_get_verified_token)]


def verify_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Verifies the JWT token and decodes the payload.

    .. deprecated::
        This function has a confusing dual-purpose signature.
        - For direct calls, use decode_and_verify_token(token) instead.
        - For FastAPI dependencies, use VerifiedToken type annotation.

    Args:
        token (str): JWT token passed via the Authorization header.

    Raises:
        HTTPException: If token is invalid or expired.

    Returns:
        dict: The decoded payload.
    """
    warnings.warn(
        "verify_token() is deprecated. Use decode_and_verify_token() for direct calls "
        "or VerifiedToken for FastAPI dependencies.",
        DeprecationWarning,
        stacklevel=2
    )
    # If called as a dependency, token might be provided by Depends(oauth2_scheme)
    # If called directly, token is passed as argument.
    return decode_and_verify_token(token)


# Verify Refresh Token
def verify_refresh_token(token: str) -> dict:
    """
    Verifies refresh token and decodes payload.

    Args:
        token (str): The refresh token to verify.

    Raises:
        HTTPException: If token is invalid, expired, or wrong type.

    Returns:
        dict: The decoded payload.
    """
    try:
        payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])

        # Check expiration
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type - expected refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"}
        )


# Check if Token is Blacklisted
async def is_token_blacklisted(jti: str, db) -> bool:
    """
    Check if a token JTI is blacklisted.

    Args:
        jti (str): The JWT ID to check.
        db: Database session.

    Returns:
        bool: True if token is blacklisted, False otherwise.
    """
    from src.api.cache.redis_client import cache

    cache_key = f"token_bl:{jti}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return bool(cached)

    from sqlalchemy import select

    from src.api.models.user_models.token_blacklist import TokenBlacklist

    try:
        result = await db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == jti)
        )
        blacklisted = result.scalar_one_or_none()
        is_bl = blacklisted is not None
    except Exception as exc:
        err_str = str(exc).lower()
        if "sasl authentication failed" in err_str or "protocolviolationerror" in err_str:
            import asyncio
            try:
                loop_id = id(asyncio.get_running_loop())
            except RuntimeError:
                loop_id = "no_loop"
            logger.error(
                "DIAGNOSTIC: SASL Protocol Violation caught in is_token_blacklisted",
                extra={"error_detail": str(exc), "jti": jti, "loop_id": loop_id},
                exc_info=True,
            )
        raise

    # Only cache positive (blacklisted) results. Caching False for non-blacklisted
    # tokens creates a stale window where a just-revoked token passes the cache
    # check if blacklist_token_in_cache() failed silently (Redis error on logout).
    if is_bl:
        await cache.set(cache_key, True, ttl=3600)

    return is_bl


async def blacklist_token_in_cache(jti: str, expires_at_ts: int) -> None:
    """Write a revoked JTI to Redis immediately so the next request is denied
    without a DB round-trip. TTL is capped at the token's own expiry."""
    import time

    from src.api.cache.redis_client import cache

    remaining = max(int(expires_at_ts - time.time()), 0)
    if remaining > 0:
        await cache.set(f"token_bl:{jti}", True, ttl=remaining)
