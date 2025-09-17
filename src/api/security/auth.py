from langgraph_sdk import Auth
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from src.utils.helper import verify_token
from src.api.middleware.exceptions import (
    WrextAuthenticationException,
    TokenExpiredException,
    InvalidAPIKeyException
)

auth = Auth()
API_KEY = "supersecretapikey" 
API_KEY_NAME = "content-api-key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

@auth.authenticate
async def get_current_user(authorization: str | None) -> Auth.types.MinimalUserDict:
    """Check if the user's token is valid."""
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
    except Exception as e:
        raise WrextAuthenticationException(
            message="Token validation failed",
            context={"error_details": str(e)}
        )

    # Extract user info from JWT payload
    user_id = payload.get("sub")  # usually `sub` holds user id
    if not user_id:
        raise WrextAuthenticationException(
            message="User ID missing in token payload",
            context={"payload_keys": list(payload.keys())}
        )

    user_info = {
        "identity": user_id,
        "name": payload.get("name"),
        "email": payload.get("email"),
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
            message="API key is required",
            context={"header_name": API_KEY_NAME}
        )

    if api_key_header != API_KEY:
        raise InvalidAPIKeyException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key_header)}
        )

    return api_key_header