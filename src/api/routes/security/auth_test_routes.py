"""
Authentication Testing API endpoints.

This module provides endpoints to test API key authentication functionality.
"""

from fastapi import APIRouter, Depends, Request
from src.api.security.auth import get_api_key
from src.utils.response_utils import success

router = APIRouter(
    prefix="/auth",
    tags=["auth-testing"]
)


@router.get("/test")
async def test_api_key_auth(
    request: Request,
    api_key: str = Depends(get_api_key)
):
    """
    Test API key authentication.
    
    This endpoint requires a valid API key in the header.
    
    Headers:
    - X-API-Key: Your API key
    
    Returns:
    - Success message if API key is valid
    - 401 error if API key is missing or invalid
    """
    return success(
        data={
            "authenticated": True,
            "api_key_valid": True,
            "message": "API key authentication successful!"
        },
        request=request,
        message="Authentication test passed"
    )


@router.get("/test/protected")
async def test_protected_endpoint(
    request: Request,
    api_key: str = Depends(get_api_key)
):
    """
    Another protected endpoint to test API key authentication.
    
    This demonstrates how to use the get_api_key dependency
    to protect any endpoint.
    
    Headers:
    - X-API-Key: Your API key
    
    Returns:
    - Protected data if authenticated
    """
    return success(
        data={
            "authenticated": True,
            "protected_data": {
                "user_info": "This is protected information",
                "access_level": "authenticated",
                "timestamp": "2026-02-06T10:43:08+05:00"
            }
        },
        request=request,
        message="Access granted to protected resource"
    )


@router.get("/test/public")
async def test_public_endpoint(request: Request):
    """
    Public endpoint that doesn't require authentication.
    
    This endpoint can be accessed without an API key.
    Use this to verify your server is running correctly.
    
    Returns:
    - Public information without authentication
    """
    return success(
        data={
            "authenticated": False,
            "public_access": True,
            "message": "This endpoint doesn't require authentication"
        },
        request=request,
        message="Public endpoint accessed successfully"
    )
