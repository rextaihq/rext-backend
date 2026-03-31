"""
Shopify Integration Routes

Endpoints for managing Shopify store connections on a workspace.
Authentication: Store URL + Shopify Admin Access Token (no OAuth).
Publishing is out of scope for this module.

Base URL: /api/v1/shopify
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextExternalServiceException,
    RextValidationException,
)
from src.api.models.workspace_models.workspace_integration import WorkspaceIntegration
from src.api.schema.shopify_schema import (
    ShopifyConnectRequest,
    ShopifyConnectionResponse,
    ShopifyTestConnectionResponse,
    ShopifyUpdateRequest,
)
from src.api.security.dependencies import get_current_user
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.web.shopify import ShopifyConnector

router = APIRouter()

INTEGRATION_TYPE = "shopify"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_connection_or_404(
    db: AsyncSession, connection_id: UUID, workspace_id: UUID
) -> WorkspaceIntegration:
    """Fetch a Shopify WorkspaceIntegration or raise 404."""
    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.id == connection_id,
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.integration_type == INTEGRATION_TYPE,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise ResourceNotFoundException(
            resource_type="Shopify Connection",
            resource_id=str(connection_id),
        )
    return connection


def _serialize_connection(conn: WorkspaceIntegration) -> dict:
    """Return a safe dict representation of a Shopify connection."""
    return {
        "id": str(conn.id),
        "workspace_id": str(conn.workspace_id),
        "integration_type": conn.integration_type,
        "store_url": conn.site_url,
        "is_active": conn.is_active,
        "has_access_token": bool(conn.api_key),
        "config_json": conn.config_json,
        "created_at": conn.created_at.isoformat() if conn.created_at else None,
        "updated_at": conn.updated_at.isoformat() if conn.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/list")
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("list shopify connections", "Shopify connections retrieved")
async def list_shopify_connections(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
) -> dict:
    """List all Shopify store connections for a workspace."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    result = await db.execute(
        select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace.id,
            WorkspaceIntegration.integration_type == INTEGRATION_TYPE,
        )
    )
    connections = result.scalars().all()

    return {
        "connections": [_serialize_connection(c) for c in connections],
        "total_count": len(connections),
        "workspace_id": str(workspace.id),
    }


@router.post("/connect")
@require_permissions("content.create", workspace_scoped=True)
@db_transaction_handler("connect shopify store", "Shopify store connected successfully", auto_commit=True)
async def connect_shopify_store(
    data: ShopifyConnectRequest,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Connect a new Shopify store.

    Validates the store URL and access token by calling the Shopify Admin API
    before persisting the connection.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Test the connection before saving
    try:
        logger.info(
            f"Validating Shopify connection for store: {data.store_url}"
        )
        async with ShopifyConnector(
            store_url=data.store_url,
            access_token=data.access_token,
        ) as connector:
            shop_info = await connector.test_connection()
        logger.info(f"Shopify connection validated: {shop_info.get('name')}")
    except Exception as exc:
        logger.error(
            f"Shopify connection validation failed for store '{data.store_url}': "
            f"{type(exc).__name__}: {exc}"
        )
        raise RextValidationException(
            message=(
                "Failed to connect to Shopify store. "
                "Please verify your store URL and access token."
            ),
        )

    # Normalise the store_url the same way ShopifyConnector does
    store_url = data.store_url.strip().rstrip("/")
    if not store_url.startswith("http"):
        if not store_url.endswith(".myshopify.com"):
            store_url = f"{store_url}.myshopify.com"
        store_url = f"https://{store_url}"

    new_connection = WorkspaceIntegration(
        workspace_id=workspace.id,
        integration_type=INTEGRATION_TYPE,
        is_active=data.is_active,
        # site_url → store URL, api_key (encrypted) → access token
        site_url=store_url,
        api_key=data.access_token,
        config_json=data.config_json,
    )

    db.add(new_connection)
    await db.flush()

    return {
        "connection": _serialize_connection(new_connection),
        "shop_info": shop_info,
    }


@router.get("/{connection_id}")
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("get shopify connection", "Shopify connection retrieved")
async def get_shopify_connection(
    connection_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
) -> dict:
    """Retrieve details of a specific Shopify store connection."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    connection = await _get_connection_or_404(db, connection_id, workspace.id)
    return {"connection": _serialize_connection(connection)}


@router.patch("/{connection_id}")
@require_permissions("content.update", workspace_scoped=True)
@db_transaction_handler("update shopify connection", "Shopify connection updated successfully", auto_commit=True)
async def update_shopify_connection(
    connection_id: UUID,
    data: ShopifyUpdateRequest,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
) -> dict:
    """Update a Shopify store connection (URL, token, or active state)."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    connection = await _get_connection_or_404(db, connection_id, workspace.id)

    if data.store_url is not None:
        connection.site_url = data.store_url
    if data.access_token is not None:
        connection.api_key = data.access_token
    if data.is_active is not None:
        connection.is_active = data.is_active
    if data.config_json is not None:
        connection.config_json = data.config_json

    return {"connection": _serialize_connection(connection)}


@router.delete("/{connection_id}")
@require_permissions("content.delete", workspace_scoped=True)
@db_transaction_handler("disconnect shopify store", "Shopify store disconnected successfully", auto_commit=True)
async def disconnect_shopify_store(
    connection_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
) -> dict:
    """Disconnect (delete) a Shopify store connection."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    connection = await _get_connection_or_404(db, connection_id, workspace.id)
    await db.delete(connection)

    return {"connection_id": str(connection_id)}


@router.post("/{connection_id}/activate")
@require_permissions("content.update", workspace_scoped=True)
@db_transaction_handler("activate shopify connection", "Shopify connection activated", auto_commit=True)
async def activate_shopify_connection(
    connection_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
) -> dict:
    """Mark a Shopify connection as active."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    connection = await _get_connection_or_404(db, connection_id, workspace.id)
    connection.is_active = True

    return {"connection": _serialize_connection(connection)}


@router.post("/{connection_id}/deactivate")
@require_permissions("content.update", workspace_scoped=True)
@db_transaction_handler("deactivate shopify connection", "Shopify connection deactivated", auto_commit=True)
async def deactivate_shopify_connection(
    connection_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
) -> dict:
    """Mark a Shopify connection as inactive."""
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    connection = await _get_connection_or_404(db, connection_id, workspace.id)
    connection.is_active = False

    return {"connection": _serialize_connection(connection)}


@router.post("/{connection_id}/test")
@require_permissions("content.read", workspace_scoped=True)
@db_transaction_handler("test shopify connection", "Shopify connection test complete")
async def test_shopify_connection(
    connection_id: UUID,
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Re-test an existing Shopify store connection.

    Calls the Shopify Admin API with the stored credentials and returns
    the result without modifying the stored record.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    connection = await _get_connection_or_404(db, connection_id, workspace.id)

    if not connection.site_url or not connection.api_key:
        return {
            "result": {
                "success": False,
                "connection_id": str(connection_id),
                "store_url": connection.site_url or "",
                "shop_info": None,
                "error": "Connection is missing store URL or access token.",
            }
        }

    try:
        async with ShopifyConnector(
            store_url=connection.site_url,
            access_token=connection.api_key,
        ) as connector:
            shop_info = await connector.test_connection()

        return {
            "result": {
                "success": True,
                "connection_id": str(connection_id),
                "store_url": connection.site_url,
                "shop_info": shop_info,
                "error": None,
            }
        }

    except Exception as exc:
        logger.warning(
            f"Shopify connection test failed for {connection.site_url}: {exc}"
        )
        return {
            "result": {
                "success": False,
                "connection_id": str(connection_id),
                "store_url": connection.site_url,
                "shop_info": None,
                "error": str(exc),
            }
        }
