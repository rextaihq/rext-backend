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
- Access Token Expiration: 24 hours (configurable)
- Refresh Token Expiration: 7 days (configurable)

Note: While multiple algorithms are available, we use HS256 (HMAC) by default
for simplicity. For higher security requirements, consider using RS256 (RSA)
or ES256 (Elliptic Curve) with asymmetric key pairs.
"""

from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
import bcrypt
import jwt
import uuid

from src.api.config import get_settings

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
def create_refresh_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Creates a long-lived refresh token with JTI for blacklisting support.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to configured value.

    Returns:
        str: The JWT refresh token.
    """
    to_encode = data.copy()
    if expires_delta is None:
        expires_delta = timedelta(days=_settings.REFRESH_TOKEN_EXPIRE_DAYS)
    expire = datetime.now(timezone.utc) + expires_delta
    jti = str(uuid.uuid4())  # Unique token ID for blacklisting
    to_encode.update({
        "exp": expire,
        "jti": jti,
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

# verify password
def verify_token(token: str = Depends(oauth2_scheme), expected_type: str = None) -> dict:
    """
    Verifies the JWT token and decodes the payload.

    Args:
        token (str): JWT token passed via the Authorization header.
        expected_type (str, optional): Expected token type (e.g., 'access', 'password_reset').

    Raises:
        HTTPException: If token is invalid, expired, or has wrong type.

    Returns:
        dict: The decoded payload.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Check expiration
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Check token type if expected
        if expected_type and payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type - expected {expected_type}",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return payload
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )


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
    from src.api.models.user_models.token_blacklist import TokenBlacklist
    from sqlalchemy import select
    result = await db.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == jti)
    )
    blacklisted = result.scalar_one_or_none()
    return blacklisted is not None