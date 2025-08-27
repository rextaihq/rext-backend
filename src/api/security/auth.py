from langgraph_sdk import Auth
from fastapi import HTTPException
from src.utils.helper import verify_token

auth = Auth()

@auth.authenticate
async def get_current_user(authorization: str | None) -> Auth.types.MinimalUserDict:
    """Check if the user's token is valid."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    scheme, token = authorization.split()
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid auth scheme")

    # verify the token
    payload = verify_token(token)

    # Extract user info from JWT payload
    user_id = payload.get("sub")  # usually `sub` holds user id
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID missing in token")
    
    print("Identity: ",{
        "identity": user_id,
        "name": payload.get("name"),
        "email": payload.get("email"),
    })

    return {
        "identity": user_id,
        "name": payload.get("name"),
        "email": payload.get("email"),
    }


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