import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import settings
from src.api.database.async_database import get_async_db as get_db
from src.api.middleware.exceptions import RextValidationException
from src.api.middleware.permissions import PermissionChecker
from src.api.schema.shopify_schema import (
    ShopifyConnectRequest as ShopifyIntegrationCreate,
)
from src.api.schema.shopify_schema import (
    ShopifyInstallStartRequest,
)
from src.api.security.dependencies import get_current_user
from src.services.integration_services import IntegrationService
from src.utils.response_utils import success


class ShopifyBridgeNotifyRequest(BaseModel):
    shop: str
    access_token: str
    scopes: str


router = APIRouter(prefix="/shopify", tags=["Shopify Integration"])


@router.post("/install/start")
async def start_shopify_install(
    workspace_id: uuid.UUID,
    data: ShopifyInstallStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["integration.create"], workspace_scoped=True)),
):
    """Start the Shopify app installation flow and return the install URL."""
    service = IntegrationService(db)
    user_id = current_user.get("identity")
    if not user_id:
        raise RextValidationException(message="Authenticated user identity is missing.")

    base = (settings.BACKEND_URL or str(request.base_url)).rstrip("/")
    callback_url = f"{base}/api/v1/integrations/shopify/install/callback"
    install_url = await service.build_shopify_install_url(
        workspace_id=workspace_id,
        user_id=user_id,
        store_url=data.store_url,
        callback_url=callback_url,
        return_path=data.return_path,
    )

    return success(
        data={"install_url": install_url},
        message="Shopify installation URL generated successfully",
    )


@router.get("/install/callback", name="shopify_install_callback")
async def shopify_install_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle the Shopify OAuth callback and redirect back to the frontend."""
    service = IntegrationService(db)
    query_params = {key: value for key, value in request.query_params.items()}

    try:
        redirect_url = await service.complete_shopify_install(query_params=query_params)
    except Exception as exc:
        state = query_params.get("state")
        return_path = None
        workspace_id = None
        if state:
            try:
                payload = service._decode_install_state(state)
                return_path = payload.get("return_path")
                workspace_id = payload.get("workspace_id")
            except Exception:
                pass

        redirect_url = service.build_shopify_error_redirect(
            message=str(exc),
            return_path=return_path,
            workspace_id=workspace_id,
            shop=query_params.get("shop"),
        )

    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/")
async def get_shopify_integration(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["integration.read"], workspace_scoped=True)),
):
    """Get the current Shopify integration status and configuration."""
    service = IntegrationService(db)
    integration = await service.get_integration(workspace_id, "shopify")

    if not integration:
        return success(data={"is_active": False}, message="No Shopify integration found")

    return success(
        data={
            "id": integration.id,
            "is_active": integration.is_active,
            "shop_url": integration.credentials.get("shop_url"),
            # Don't return the full access token for security
            "access_token": ("********" if integration.credentials.get("access_token") else None),
            "scopes": (integration.config.get("scopes", []) if integration.config else []),
        },
        message="Shopify integration status retrieved",
    )


@router.post("/")
async def setup_shopify_integration(
    workspace_id: uuid.UUID,
    data: ShopifyIntegrationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["integration.create"], workspace_scoped=True)),
):
    """Setup or update Shopify integration credentials."""
    service = IntegrationService(db)

    # Test connection before saving
    await service.test_shopify_connection(data.store_url, data.access_token)

    # Get access scopes (permissions)
    scopes = await service.get_shopify_scopes(data.store_url, data.access_token)

    integration = await service.create_or_update_integration(
        workspace_id=workspace_id,
        provider="shopify",
        credentials={"shop_url": data.store_url, "access_token": data.access_token},
        config={"scopes": scopes},
        is_active=True,
    )

    await db.commit()
    return success(
        data={"id": integration.id, "scopes": scopes},
        message="Shopify integration configured successfully",
    )


@router.post("/test")
async def test_shopify_connection(
    workspace_id: uuid.UUID,
    data: ShopifyIntegrationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["integration.create"], workspace_scoped=True)),
):
    """Test the Shopify API connection with provided credentials and return detected scopes."""
    service = IntegrationService(db)
    await service.test_shopify_connection(data.store_url, data.access_token)
    scopes = await service.get_shopify_scopes(data.store_url, data.access_token)
    return success(data={"scopes": scopes}, message="Shopify connection test successful")


@router.delete("/")
async def delete_shopify_integration(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["integration.delete"], workspace_scoped=True)),
):
    """Remove the Shopify integration."""
    service = IntegrationService(db)
    await service.delete_integration(workspace_id, "shopify")
    await db.commit()
    return success(message="Shopify integration removed")


@router.post("/bridge/notify")
async def shopify_bridge_notify(
    data: ShopifyBridgeNotifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the Shopify App (bridge) after successful OAuth install.
    Registers the store + access token in ShopifyAppInstall table.
    Authenticated via SHOPIFY_BRIDGE_SHARED_SECRET header.
    """
    shared_secret = request.headers.get("X-Rext-Bridge-Secret", "")
    if shared_secret != settings.SHOPIFY_BRIDGE_SHARED_SECRET:
        raise RextValidationException(message="Invalid bridge secret.")

    service = IntegrationService(db)
    await service.register_bridge_install(
        shop=data.shop,
        access_token=data.access_token,
        scopes=data.scopes,
    )
    await db.commit()
    return success(message="Bridge install registered successfully.")
