from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
from dotenv import load_dotenv
import bcrypt
import jwt,os

load_dotenv()

SECRET_KEY= os.getenv("SECRET_KEY")
ALGORITHM= os.getenv("ALGORITHM")
REFRESH_SECRET_KEY = os.getenv('REFRESH_SECRET_KEY')
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
def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifies that a plain text password matches the hashed password.

    Args:
        password (str): The plain text password.
        hashed_password (str): The hashed password from the database.

    Returns:
        bool: True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# Create Access Token
def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=24)) -> str:
    """
    Creates a JWT access token.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to 1 hour.

    Returns:
        str: The JWT token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token

# Refresh token
def create_refresh_token(data: dict, expires_delta: timedelta = timedelta(days=7)) -> str:
    """Creates a long-lived refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)


# Reset Token
def create_reset_token(data: dict, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    """
    Creates a JWT token for password reset.

    Args:
        data (dict): The payload to include in the token.
        expires_delta (timedelta, optional): Token expiration time. Defaults to 30 minutes.

    Returns:
        str: The JWT token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
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
def verify_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Verifies the JWT token and decodes the payload.

    Args:
        token (str): JWT token passed via the Authorization header.

    Raises:
        HTTPException: If token is invalid or expired.

    Returns:
        dict: The decoded payload.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )