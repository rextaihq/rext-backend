"""
License validation and management API endpoints.

This module provides endpoints for validating LemonSqueezy license keys,
managing license activations, and controlling license access.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import require_permissions
from src.api.schema.subscription import (
    LicenseValidateRequest,
    LicenseValidateResponse
)
from src.api.schema.subscription.license_schemas import (
    LicenseActivateRequest,
    LicenseDeactivateRequest,
    LicenseRevokeRequest
)
from src.providers.payment.provider_factory import get_payment_provider_singleton
from src.services.license_service import LicenseService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler
from src.utils.logger import logger
from src.api.routes.subscriptions.admin.shared.auth import require_super_admin
from src.api.middleware.rate_limiter import (
    license_validate_rate_limit,
    license_activate_rate_limit,
    license_deactivate_rate_limit,
    license_revoke_rate_limit
)


router = APIRouter(
    prefix="/licenses",
    tags=["licenses"]
)


@router.post("/validate", response_model=dict, status_code=status.HTTP_200_OK)
@require_permissions("license.read", workspace_scoped=False)
@db_transaction_handler("validate license key", auto_commit=False)
async def validate_license(
    request: Request,
    license_data: LicenseValidateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(license_validate_rate_limit())
):
    """
    Validate a LemonSqueezy license key.

    Required Permission: license.read (user-level)
    Scope: User-level (not workspace-scoped)

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
    user_id = current_user.get("identity")
    logger.info(
        f"License validation request for key: {license_data.license_key[:8]}...",
        extra={
            "user_id": user_id,
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
            data=response_data.model_dump(),
            request=request,
            message="License validated successfully"
        )

    except Exception as e:
        logger.error(
            "License validation failed",
            exc_info=True,
            extra={
                "license_key_prefix": license_data.license_key[:8]
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="License validation failed. Please check your key and try again."
        )


# ============================================================================
# LICENSE ACTIVATION MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/activate", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("activate license")
@require_permissions("license.activate", workspace_scoped=False)
async def activate_license_endpoint(
    request: Request,
    activation_data: LicenseActivateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(license_activate_rate_limit())
):
    """
    Activate a license key for a specific device/instance.

    This endpoint claims a license key and activates it for the specified
    instance (device, domain, etc.). If the license has already been claimed
    by another user, this will fail.

    Body:
    - license_key: The license key to activate
    - instance_id: Unique identifier for the device/instance
    - instance_name: Optional human-readable name for the instance

    Returns:
    - Activation details including license and activation information

    Raises:
    - 404: License key not found
    - 400: License expired, disabled, or activation limit reached
    - 403: License owned by another user
    - 409: Instance already activated
    """
    user_id = current_user.get("identity")
    service = LicenseService(db)

    # Get request metadata
    metadata = {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }

    # Activate license
    activation = await service.activate_license(
        user_id=user_id,
        license_key=activation_data.license_key,
        instance_id=activation_data.instance_id,
        instance_name=activation_data.instance_name,
        metadata=metadata
    )

    # Get the license for response (use await for async relationship loading)
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select as sa_select
    from src.api.models.subscription_models.license_activations import LicenseActivation

    # Refetch activation with license eagerly loaded
    stmt = sa_select(LicenseActivation).where(
        LicenseActivation.id == activation.id
    ).options(selectinload(LicenseActivation.license))
    result = await db.execute(stmt)
    activation = result.scalar_one()
    license_obj = activation.license

    return success(
        data={
            "activation": {
                "id": str(activation.id),
                "license_id": str(activation.license_id),
                "instance_id": activation.instance_id,
                "instance_name": activation.instance_name,
                "is_active": activation.is_active,
                "activated_at": activation.activated_at.isoformat(),
                "deactivated_at": activation.deactivated_at.isoformat() if activation.deactivated_at else None
            },
            "license": {
                "id": str(license_obj.id),
                "license_key": license_obj.license_key,
                "product_name": license_obj.product_name,
                "status": license_obj.status.value,
                "activation_limit": license_obj.activation_limit,
                "activation_count": license_obj.activation_count,
                "expires_at": license_obj.expires_at.isoformat() if license_obj.expires_at else None
            }
        },
        request=request,
        message="License activated successfully"
    )


@router.post("/{license_id}/deactivate", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("deactivate license")
@require_permissions("license.deactivate", workspace_scoped=False)
async def deactivate_license_endpoint(
    request: Request,
    license_id: str,
    deactivation_data: LicenseDeactivateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(license_deactivate_rate_limit())
):
    """
    Deactivate a license activation for a specific instance.

    This frees up an activation slot, allowing the license to be activated
    on a different device/instance.

    Path Parameters:
    - license_id: UUID of the license

    Body:
    - instance_id: Instance identifier to deactivate

    Returns:
    - Deactivation confirmation

    Raises:
    - 404: License or activation not found
    - 403: User doesn't own the license
    - 400: Activation already inactive
    """
    user_id = current_user.get("identity")
    service = LicenseService(db)

    # Deactivate
    activation = await service.deactivate_license(
        user_id=user_id,
        license_id=UUID(license_id),
        instance_id=deactivation_data.instance_id
    )

    return success(
        data={
            "id": str(activation.id),
            "instance_id": activation.instance_id,
            "is_active": activation.is_active,
            "deactivated_at": activation.deactivated_at.isoformat() if activation.deactivated_at else None
        },
        request=request,
        message="License deactivated successfully"
    )


@router.get("", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("list licenses", auto_commit=False)
@require_permissions("license.read", workspace_scoped=False)
async def list_licenses_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all licenses owned by the current user.

    Returns:
    - List of licenses with details

    Raises:
    - 401: Unauthorized
    """
    user_id = current_user.get("identity")
    service = LicenseService(db)

    # Get licenses
    licenses = await service.get_user_licenses(user_id)

    # Format response
    licenses_data = []
    for lic in licenses:
        licenses_data.append({
            "id": str(lic.id),
            "license_key": lic.license_key,
            "product_name": lic.product_name,
            "status": lic.status.value,
            "activation_limit": lic.activation_limit,
            "activation_count": lic.activation_count,
            "activated_at": lic.activated_at.isoformat() if lic.activated_at else None,
            "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
            "created_at": lic.created_at.isoformat()
        })

    return success(
        data={
            "licenses": licenses_data,
            "total": len(licenses_data)
        },
        request=request,
        message="Licenses retrieved successfully"
    )


@router.get("/{license_id}", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("get license details", auto_commit=False)
@require_permissions("license.read", workspace_scoped=False)
async def get_license_endpoint(
    request: Request,
    license_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get details of a specific license.

    Path Parameters:
    - license_id: UUID of the license

    Returns:
    - License details

    Raises:
    - 404: License not found
    - 403: User doesn't own the license
    """
    user_id = current_user.get("identity")
    service = LicenseService(db)

    # Get license
    license_obj = await service.get_license_by_id(UUID(license_id))

    if not license_obj:
        from src.api.middleware.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException(
            resource_type="License",
            resource_id=license_id,
            message="License not found"
        )

    # Check ownership
    if license_obj.user_id != user_id:
        from src.api.middleware.exceptions import RextAuthorizationException
        raise RextAuthorizationException(
            message="You do not own this license",
            required_permission="license.read"
        )

    return success(
        data={
            "id": str(license_obj.id),
            "license_key": license_obj.license_key,
            "product_name": license_obj.product_name,
            "status": license_obj.status.value,
            "activation_limit": license_obj.activation_limit,
            "activation_count": license_obj.activation_count,
            "activated_at": license_obj.activated_at.isoformat() if license_obj.activated_at else None,
            "expires_at": license_obj.expires_at.isoformat() if license_obj.expires_at else None,
            "created_at": license_obj.created_at.isoformat()
        },
        request=request,
        message="License retrieved successfully"
    )


@router.get("/{license_id}/activations", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("list license activations", auto_commit=False)
@require_permissions("license.read", workspace_scoped=False)
async def list_license_activations_endpoint(
    request: Request,
    license_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all activations for a specific license.

    Shows both active and deactivated instances.

    Path Parameters:
    - license_id: UUID of the license

    Returns:
    - List of activations

    Raises:
    - 404: License not found
    - 403: User doesn't own the license
    """
    user_id = current_user.get("identity")
    service = LicenseService(db)

    # Get activations (includes ownership check)
    activations = await service.get_license_activations(user_id, UUID(license_id))

    # Format response
    activations_data = []
    active_count = 0
    for act in activations:
        if act.is_active:
            active_count += 1

        activations_data.append({
            "id": str(act.id),
            "license_id": str(act.license_id),
            "instance_id": act.instance_id,
            "instance_name": act.instance_name,
            "is_active": act.is_active,
            "activated_at": act.activated_at.isoformat(),
            "deactivated_at": act.deactivated_at.isoformat() if act.deactivated_at else None
        })

    return success(
        data={
            "activations": activations_data,
            "total": len(activations_data),
            "active_count": active_count
        },
        request=request,
        message="Activations retrieved successfully"
    )


@router.post("/admin/{license_id}/revoke", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("revoke license")
@require_permissions("license.revoke", workspace_scoped=False)
async def revoke_license_endpoint(
    request: Request,
    license_id: str,
    revoke_data: LicenseRevokeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(license_revoke_rate_limit())
):
    """
    Revoke a license (admin only).

    This disables the license and deactivates all active instances.
    Used for license violations, refunds, or other admin actions.

    Path Parameters:
    - license_id: UUID of the license to revoke

    Body:
    - reason: Optional reason for revocation

    Returns:
    - Revocation confirmation

    Raises:
    - 404: License not found
    - 403: Not authorized (admin only)
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = LicenseService(db)

    # Revoke license
    license_obj = await service.revoke_license(
        license_id=UUID(license_id),
        revoked_by_user_id=admin_user_id
    )

    return success(
        data={
            "id": str(license_obj.id),
            "license_key": license_obj.license_key,
            "status": license_obj.status.value,
            "revoked_by": str(admin_user_id),
            "reason": revoke_data.reason
        },
        request=request,
        message="License revoked successfully"
    )
