"""
Integration service for workspace-scoped provider connections.

This project stores integrations in the generic ``WorkspaceIntegration`` model.
The service below is built around that schema and adds a small compatibility
layer for route code that still expects ``credentials`` and ``config`` attrs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
import uuid

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import settings
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.integrations.shopify_app_install import ShopifyAppInstall
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.utils.logger import logger
from src.web.shopify import ShopifyConnector, SHOPIFY_API_VERSION
from src.web.shopify_bridge import normalize_store_url


class IntegrationService:
    """Service for reading and writing provider integrations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _normalized_shop_domain(store_url: str) -> str:
        """Return canonical shop domain without URL scheme."""
        return normalize_store_url(store_url).replace("https://", "", 1)

    def _shopify_scopes(self) -> str:
        return ",".join(
            scope.strip()
            for scope in settings.SHOPIFY_APP_SCOPES.split(",")
            if scope.strip()
        )

    def _frontend_return_url(
        self,
        *,
        status: str,
        shop: Optional[str] = None,
        workspace_id: Optional[str] = None,
        return_path: Optional[str] = None,
        error: Optional[str] = None,
    ) -> str:
        base_frontend = settings.FRONTEND_URL.rstrip("/")
        target_path = (return_path or settings.SHOPIFY_INTEGRATION_RETURN_PATH).strip()
        if not target_path.startswith("/"):
            target_path = f"/{target_path}"

        params = {"provider": "shopify", "status": status}
        if shop:
            params["shop"] = shop
        if workspace_id:
            params["workspace_id"] = workspace_id
        if error:
            params["error"] = error

        return f"{base_frontend}{target_path}?{urlencode(params)}"

    def _create_install_state(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: str,
        shop_domain: str,
        return_path: Optional[str],
    ) -> str:
        payload = {
            "workspace_id": str(workspace_id),
            "user_id": user_id,
            "shop": shop_domain,
            "return_path": return_path or settings.SHOPIFY_INTEGRATION_RETURN_PATH,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            "type": "shopify_install_state",
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def _decode_install_state(self, state: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(
                state,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
            )
        except jwt.PyJWTError as exc:
            raise RextValidationException(
                message="Invalid or expired Shopify install state."
            ) from exc

        if payload.get("type") != "shopify_install_state":
            raise RextValidationException(message="Invalid Shopify install state.")

        return payload

    def _verify_shopify_callback_hmac(self, query_params: Dict[str, str]) -> None:
        hmac_value = query_params.get("hmac")
        if not hmac_value:
            raise RextValidationException(message="Missing Shopify callback signature.")

        message_parts = []
        for key in sorted(query_params.keys()):
            if key in {"hmac", "signature"}:
                continue
            value = query_params[key]
            message_parts.append(f"{key}={value}")
        message = "&".join(message_parts)

        digest = hmac.new(
            settings.SHOPIFY_API_SECRET.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(digest, hmac_value):
            raise RextValidationException(message="Invalid Shopify callback signature.")

    async def _exchange_shopify_code_for_token(
        self, *, shop_domain: str, code: str
    ) -> Dict[str, Any]:
        token_url = f"https://{shop_domain}/admin/oauth/access_token"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                token_url,
                json={
                    "client_id": settings.SHOPIFY_API_KEY,
                    "client_secret": settings.SHOPIFY_API_SECRET,
                    "code": code,
                },
            )

        if response.status_code != 200:
            raise RextValidationException(
                message="Failed to exchange Shopify authorization code for access token."
            )

        return response.json()

    async def build_shopify_install_url(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: str,
        store_url: str,
        callback_url: str,
        return_path: Optional[str] = None,
    ) -> str:
        """Build the Shopify OAuth install URL for a workspace."""
        if not settings.SHOPIFY_API_KEY or not settings.SHOPIFY_API_SECRET:
            raise RextValidationException(
                message="Shopify app credentials are not configured on the backend."
            )

        shop_domain = self._normalized_shop_domain(store_url)
        state = self._create_install_state(
            workspace_id=workspace_id,
            user_id=user_id,
            shop_domain=shop_domain,
            return_path=return_path,
        )

        params = {
            "client_id": settings.SHOPIFY_API_KEY,
            "scope": self._shopify_scopes(),
            "redirect_uri": callback_url,
            "state": state,
        }
        return f"https://{shop_domain}/admin/oauth/authorize?{urlencode(params)}"

    async def complete_shopify_install(
        self,
        *,
        query_params: Dict[str, str],
    ) -> str:
        """
        Complete Shopify installation and return the frontend redirect URL.
        """
        if not settings.SHOPIFY_API_KEY or not settings.SHOPIFY_API_SECRET:
            raise RextValidationException(
                message="Shopify app credentials are not configured on the backend."
            )

        self._verify_shopify_callback_hmac(query_params)

        state = query_params.get("state")
        code = query_params.get("code")
        shop = query_params.get("shop")

        if not state or not code or not shop:
            raise RextValidationException(
                message="Missing required Shopify callback parameters."
            )

        state_payload = self._decode_install_state(state)
        shop_domain = self._normalized_shop_domain(shop)

        if state_payload.get("shop") != shop_domain:
            raise RextValidationException(
                message="Shopify callback shop does not match the install request."
            )

        token_payload = await self._exchange_shopify_code_for_token(
            shop_domain=shop_domain,
            code=code,
        )
        access_token = (token_payload.get("access_token") or "").strip()
        scopes = token_payload.get("scope") or self._shopify_scopes()
        if not access_token:
            raise RextValidationException(
                message="Shopify did not return an access token."
            )

        workspace_id = uuid.UUID(state_payload["workspace_id"])
        user_id = uuid.UUID(state_payload["user_id"])
        normalized_store_url = normalize_store_url(shop_domain)
        scopes_list = [scope.strip() for scope in scopes.split(",") if scope.strip()]

        install_result = await self.db.execute(
            select(ShopifyAppInstall).where(ShopifyAppInstall.shop_url == shop_domain)
        )
        install = install_result.scalar_one_or_none()
        if install:
            install.access_token = access_token
            install.scopes = scopes
            install.workspace_id = workspace_id
            install.linked_by = user_id
            install.linked_at = datetime.now(timezone.utc)
        else:
            install = ShopifyAppInstall(
                shop_url=shop_domain,
                access_token=access_token,
                scopes=scopes,
                workspace_id=workspace_id,
                linked_by=user_id,
                linked_at=datetime.now(timezone.utc),
            )
            self.db.add(install)

        await self.create_or_update_integration(
            workspace_id=workspace_id,
            provider="shopify",
            credentials={
                "shop_url": normalized_store_url,
                "access_token": access_token,
            },
            config={"scopes": scopes_list, "connection_mode": "oauth_install"},
            is_active=True,
        )

        await self.db.flush()
        await self.db.commit()

        return self._frontend_return_url(
            status="connected",
            shop=shop_domain,
            workspace_id=str(workspace_id),
            return_path=state_payload.get("return_path"),
        )

    async def register_bridge_install(
        self,
        *,
        shop: str,
        access_token: str,
        scopes: str,
    ) -> None:
        """Register a Shopify store install coming from the bridge app (no workspace link)."""
        shop_domain = self._normalized_shop_domain(shop)
        result = await self.db.execute(
            select(ShopifyAppInstall).where(ShopifyAppInstall.shop_url == shop_domain)
        )
        install = result.scalar_one_or_none()
        if install:
            install.access_token = access_token
            install.scopes = scopes
        else:
            install = ShopifyAppInstall(
                shop_url=shop_domain,
                access_token=access_token,
                scopes=scopes,
            )
            self.db.add(install)

    def build_shopify_error_redirect(
        self,
        *,
        message: str,
        return_path: Optional[str] = None,
        workspace_id: Optional[str] = None,
        shop: Optional[str] = None,
    ) -> str:
        """Build a frontend redirect URL for failed/cancelled installs."""
        return self._frontend_return_url(
            status="error",
            shop=shop,
            workspace_id=workspace_id,
            return_path=return_path,
            error=message,
        )

    def _hydrate_legacy_fields(
        self, integration: WorkspaceIntegration
    ) -> WorkspaceIntegration:
        """
        Expose compatibility attributes used by the legacy integration routes.

        The current model stores Shopify data in ``site_url``, ``api_key``, and
        ``config_json``. Older route code expects ``credentials`` and ``config``.
        """
        integration.credentials = {
            "shop_url": integration.site_url,
            "access_token": integration.api_key,
        }
        integration.config = integration.config_json or {}
        integration.provider = integration.integration_type
        return integration

    async def _get_workspace_integration(
        self,
        workspace_id: uuid.UUID,
        provider: str,
    ) -> Optional[WorkspaceIntegration]:
        """Return the most recently updated non-deleted integration for a provider."""
        result = await self.db.execute(
            select(WorkspaceIntegration)
            .where(
                WorkspaceIntegration.workspace_id == workspace_id,
                WorkspaceIntegration.integration_type == provider,
                WorkspaceIntegration.deleted_at.is_(None),
            )
            .order_by(
                WorkspaceIntegration.updated_at.desc(),
                WorkspaceIntegration.created_at.desc(),
            )
        )
        return result.scalars().first()

    async def get_integration(
        self,
        workspace_id: uuid.UUID,
        provider: str,
    ) -> Optional[WorkspaceIntegration]:
        """Get a workspace integration by provider."""
        integration = await self._get_workspace_integration(workspace_id, provider)
        if not integration:
            return None
        return self._hydrate_legacy_fields(integration)

    async def create_or_update_integration(
        self,
        workspace_id: uuid.UUID,
        provider: str,
        credentials: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        is_active: bool = True,
    ) -> WorkspaceIntegration:
        """
        Create or update a workspace-scoped integration.

        Only Shopify is supported by this compatibility service today.
        """
        if provider != "shopify":
            raise RextValidationException(
                message=f"Unsupported integration provider: {provider}"
            )

        shop_url = normalize_store_url(
            credentials.get("shop_url") or credentials.get("store_url") or ""
        )
        access_token = (credentials.get("access_token") or "").strip()
        if not access_token:
            raise RextValidationException(
                message="Shopify access token is required."
            )

        integration = await self._get_workspace_integration(workspace_id, provider)

        if integration:
            integration.site_url = shop_url
            integration.api_key = access_token
            if config is not None:
                integration.config_json = config
            integration.is_active = is_active
        else:
            integration = WorkspaceIntegration(
                workspace_id=workspace_id,
                integration_type=provider,
                site_url=shop_url,
                api_key=access_token,
                config_json=config,
                is_active=is_active,
            )
            self.db.add(integration)

        await self.db.flush()
        await self.db.refresh(integration)

        logger.info(
            "Integration saved",
            extra={
                "workspace_id": str(workspace_id),
                "provider": provider,
                "integration_id": str(integration.id),
            },
        )

        return self._hydrate_legacy_fields(integration)

    async def delete_integration(
        self,
        workspace_id: uuid.UUID,
        provider: str,
    ) -> None:
        """Delete a workspace-scoped integration."""
        integration = await self._get_workspace_integration(workspace_id, provider)
        if not integration:
            raise ResourceNotFoundException(
                resource_type="Integration",
                message=f"Integration for provider '{provider}' not found",
            )

        await self.db.delete(integration)
        await self.db.flush()

    async def test_shopify_connection(self, shop_url: str, access_token: str) -> bool:
        """Validate Shopify credentials by calling the Admin API."""
        clean_token = (access_token or "").strip()
        if not clean_token:
            raise RextValidationException(
                message="Shopify access token is required."
            )

        async with ShopifyConnector(
            store_url=shop_url,
            access_token=clean_token,
        ) as connector:
            await connector.test_connection()

        return True

    async def get_shopify_scopes(
        self, shop_url: str, access_token: str
    ) -> List[str]:
        """Fetch Shopify Admin API scopes for the provided token."""
        clean_token = (access_token or "").strip()
        if not clean_token:
            return []

        normalized_store_url = normalize_store_url(shop_url)
        endpoint = (
            f"{normalized_store_url}/admin/oauth/access_scopes.json"
            f"?api_version={SHOPIFY_API_VERSION}"
        )

        try:
            async with httpx.AsyncClient(
                headers={
                    "X-Shopify-Access-Token": clean_token,
                    "Accept": "application/json",
                },
                timeout=15.0,
            ) as client:
                response = await client.get(endpoint)

            if response.status_code != 200:
                logger.warning(
                    "Unable to fetch Shopify scopes",
                    extra={
                        "store_url": normalized_store_url,
                        "status_code": response.status_code,
                    },
                )
                return []

            data = response.json()
            scopes = data.get("access_scopes", [])
            return [
                scope.get("handle")
                for scope in scopes
                if isinstance(scope, dict) and scope.get("handle")
            ]
        except Exception as exc:
            logger.warning(
                f"Unable to fetch Shopify scopes for {normalized_store_url}: {exc}"
            )
            return []

    async def get_active_integrations(
        self, workspace_id: uuid.UUID
    ) -> List[WorkspaceIntegration]:
        """Get active integrations for a workspace."""
        result = await self.db.execute(
            select(WorkspaceIntegration).where(
                WorkspaceIntegration.workspace_id == workspace_id,
                WorkspaceIntegration.is_active.is_(True),
                WorkspaceIntegration.deleted_at.is_(None),
            )
        )
        return [self._hydrate_legacy_fields(item) for item in result.scalars().all()]

    async def get_integrations(
        self,
        workspace_id: uuid.UUID,
        *,
        provider: Optional[str] = None,
        active_only: bool = False,
    ) -> List[WorkspaceIntegration]:
        """Get workspace integrations with optional provider and active filters."""
        query = select(WorkspaceIntegration).where(
            WorkspaceIntegration.workspace_id == workspace_id,
            WorkspaceIntegration.deleted_at.is_(None),
        )

        if provider:
            query = query.where(WorkspaceIntegration.integration_type == provider)

        if active_only:
            query = query.where(WorkspaceIntegration.is_active.is_(True))

        query = query.order_by(
            WorkspaceIntegration.updated_at.desc(),
            WorkspaceIntegration.created_at.desc(),
        )

        result = await self.db.execute(query)
        return [self._hydrate_legacy_fields(item) for item in result.scalars().all()]
