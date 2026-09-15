import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db as get_db
from src.api.middleware.permissions import PermissionChecker
from src.api.schema.response.content_responses import IntegrationListResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.integration_services import IntegrationService
from src.utils.response_utils import success

router = APIRouter(tags=["Integrations"])


@router.get("/", response_model=SuccessResponse[IntegrationListResponse])
async def list_integrations(
    workspace_id: uuid.UUID,
    provider: Optional[str] = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(PermissionChecker(["integration.read"], workspace_scoped=True)),
):
    """List all integrations for a workspace, optionally filtered by provider."""
    service = IntegrationService(db)
    integrations = await service.get_integrations(
        workspace_id,
        provider=provider.lower() if provider else None,
        active_only=active_only,
    )

    return success(
        data={
            "integrations": [integration.to_dict() for integration in integrations],
            "total_count": len(integrations),
            "workspace_id": workspace_id,
        },
        message="Integrations retrieved successfully",
    )
