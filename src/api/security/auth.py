from langgraph_sdk import Auth
from fastapi import Security
from fastapi.security.api_key import APIKeyHeader
from src.api.middleware.exceptions import InvalidAPIKeyException
from src.api.config import get_settings

# Get settings instance
settings = get_settings()

auth = Auth()
API_KEY = settings.API_KEY
API_KEY_NAME = settings.API_KEY_NAME
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


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