"""
Test endpoint for API key authentication verification.
This endpoint is used to test the timing attack fix in get_api_key.
"""

from fastapi import APIRouter, Depends, Request
from src.api.security.auth import get_api_key
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.__response__.test_responses import APIKeyCheckResponse
from src.utils.response_utils import success

router = APIRouter(prefix="/test", tags=["Testing"])


@router.get("/api-key-check", response_model=SuccessResponse[APIKeyCheckResponse])
async def test_api_key_authentication(request: Request, api_key: str = Depends(get_api_key)):
    """
    Test endpoint to verify API key authentication works correctly.
    
    This endpoint requires a valid API key in the X-API-Key header.
    
    Headers:
        X-API-Key: Your API key (must match API_KEY in .env)
    
    Returns:
        Success message if API key is valid
        
    Raises:
        InvalidAPIKeyException: If API key is missing or invalid
    """
    return success(
        data={
            "status": "success",
            "api_key_preview": api_key[:10] + "..." if len(api_key) > 10 else api_key,
            "note": "This endpoint uses constant-time comparison (hmac.compare_digest) to prevent timing attacks"
        },
        request=request,
        message="API key authentication successful"
    )
