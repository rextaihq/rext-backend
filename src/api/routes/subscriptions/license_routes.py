"""
License validation API endpoints.

This module provides endpoints for validating LemonSqueezy license keys,
typically used for lifetime deals and one-time purchases.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.subscription import (
    LicenseValidateRequest,
    LicenseValidateResponse
)
from src.services.payment.provider_factory import get_payment_provider_singleton
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler
from src.utils.logger import logger


router = APIRouter(
    prefix="/licenses",
    tags=["licenses"]
)


@router.post("/validate", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("validate license key", auto_commit=False)
async def validate_license(
    request: Request,
    license_data: LicenseValidateRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Validate a LemonSqueezy license key.

    This endpoint validates license keys for lifetime deals and one-time purchases.
    It checks the license status, activation limits, and expiration.

    Body:
    - license_key: License key to validate (required)
    - instance_id: Optional device/instance identifier for activation tracking

    Returns:
    - valid: Whether the license is valid
    - status: License status (active, inactive, expired, etc.)
    - activated: Whether license is activated
    - activation_limit: Maximum activations allowed
    - activation_usage: Current activation count
    - expires_at: Expiration date (if any)
    - customer info and product details

    Example Response:
    ```json
    {
      "valid": true,
      "license_key": "ABCD-1234-EFGH-5678",
      "status": "active",
      "activated": true,
      "activation_limit": 5,
      "activation_usage": 2,
      "expires_at": null,
      "customer_email": "user@example.com",
      "product_name": "Lifetime Pro Plan"
    }
    ```
    """
    logger.info(
        f"License validation request for key: {license_data.license_key[:8]}...",
        extra={
            "license_key_prefix": license_data.license_key[:8],
            "has_instance_id": bool(license_data.instance_id)
        }
    )

    # Get payment provider
    payment_provider = get_payment_provider_singleton()

    try:
        # Validate license with payment provider
        validation_result = await payment_provider.validate_license_key(
            license_key=license_data.license_key,
            instance_id=license_data.instance_id
        )

        logger.info(
            f"License validation successful: {validation_result.get('valid', False)}",
            extra={
                "license_key_prefix": license_data.license_key[:8],
                "status": validation_result.get('status'),
                "valid": validation_result.get('valid')
            }
        )

        # Format response
        response_data = LicenseValidateResponse(
            valid=validation_result.get("valid", False),
            license_key=license_data.license_key,
            status=validation_result.get("status", "unknown"),
            activated=validation_result.get("activated", False),
            activation_limit=validation_result.get("activation_limit"),
            activation_usage=validation_result.get("activation_usage"),
            expires_at=validation_result.get("expires_at").isoformat() if validation_result.get("expires_at") else None,
            customer_email=validation_result.get("customer_email"),
            customer_name=validation_result.get("customer_name"),
            product_name=validation_result.get("product_name"),
            variant_name=validation_result.get("variant_name")
        )

        return success(
            data=response_data.dict(),
            request=request,
            message="License validated successfully"
        )

    except Exception as e:
        logger.error(
            f"License validation failed: {str(e)}",
            extra={
                "license_key_prefix": license_data.license_key[:8],
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"License validation failed: {str(e)}"
        )
