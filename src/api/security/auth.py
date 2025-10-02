import os
from langgraph_sdk import Auth
from fastapi import HTTPException, Security, Depends
from fastapi import Header
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from src.api.security.token_utils import verify_token, is_token_blacklisted
from src.api.middleware.exceptions import (
    WrextAuthenticationException,
    TokenExpiredException,
    InvalidAPIKeyException
)
from dotenv import  load_dotenv
load_dotenv()

auth = Auth()
API_KEY = os.getenv("API_KEY")
API_KEY_NAME = os.getenv("API_KEY_NAME")
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# @auth.authenticate
def get_current_user(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
) -> Auth.types.MinimalUserDict:
    """Check if the user's token is valid and not blacklisted."""
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
        if jti and is_token_blacklisted(jti, db):
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
    }

    print("Identity verified:", user_info)
    return user_info


@auth.on
async def add_owner(
    ctx: Auth.types.AuthContext, 
    value: dict, 
):
    filters = {"owner": ctx.user.identity}
    metadata = value.setdefault("metadata", {})
    metadata.update(filters)

    # Only let users see their own resources
    return filters

def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header:
        raise InvalidAPIKeyException(
            message="API key is required"
        )

    if api_key_header != API_KEY:
        raise InvalidAPIKeyException(
            message="Invalid API key provided"
        )

    return api_key_header