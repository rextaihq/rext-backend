from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextAuthorizationException
from src.api.schema.knowledge_schema import BrandSchema
from src.api.schema.response.workspace_responses import (
    BrandVoiceRefreshResponse,
    BrandVoiceStateResponse,
    BrandVoiceWrapperResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.brand_voice_service import BrandVoiceService
from src.services.workspace_service import WorkspaceService
from src.utils import rbac_utils
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_workspace_for_route

router = APIRouter(tags=["workspace-brand-voice"])


def _serialize_brand_voice(brand_voice) -> dict:
    """Serialize BrandVoice ORM model into API response payload."""
    return {
        "id": str(brand_voice.id) if getattr(brand_voice, "id", None) else None,
        "workspace_id": str(brand_voice.workspace_id),
        "brand_name": brand_voice.brand_name,
        "about": brand_voice.about,
        "customer_profile": brand_voice.customer_profile,
        "selling_position": brand_voice.selling_position,
        "target_audience": brand_voice.target_audience or [],
        "brand_voice": brand_voice.brand_voice or [],
        "competitors": brand_voice.competitors or [],
        "content_pillar": brand_voice.content_pillar or [],
        "content_strategy": brand_voice.content_pillar or [],  # Backward compatibility
        "personas": [
            p.to_dict() for p in (brand_voice.workspace.personas if brand_voice.workspace else [])
        ],
        "site_compliance": brand_voice.site_compliance,  # ← ADD THIS LINE
        "created_at": brand_voice.created_at.isoformat()
        if getattr(brand_voice, "created_at", None)
        else None,
        "updated_at": brand_voice.updated_at.isoformat()
        if getattr(brand_voice, "updated_at", None)
        else None,
    }


async def _update_brand_voice(
    *,
    db: AsyncSession,
    brand_data: BrandSchema,
    workspace_identifier: str,
    user: dict,
) -> dict:
    """Shared handler logic for brand voice upsert operations."""
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_identifier, user=user
    )
    user_id = UUID(str(user.get("identity")))

    service = BrandVoiceService(db)
    required_permission = "brand_voice.update"
    is_super = "super_admin" in (user.get("roles") or []) or await rbac_utils.is_user_super_admin(
        db, user_id
    )
    if not is_super and not await rbac_utils.check_all_permissions(
        db, user_id, [required_permission], workspace.id
    ):
        raise RextAuthorizationException(
            message="You do not have permission to update this brand voice",
            context={"required_permission": required_permission},
        )
    brand_voice = await service.upsert_brand_voice(
        workspace_id=workspace.id,
        user_id=user_id,
        brand_data=brand_data,
    )

    return {"brand_voice": _serialize_brand_voice(brand_voice)}


@router.put(
    "/{workspace_id}/brand-voice", response_model=SuccessResponse[BrandVoiceWrapperResponse]
)
@db_transaction_handler("update brand voice", "Brand voice updated successfully")
@require_permissions("brand_voice.update", workspace_scoped=True)
async def update_brand_voice_restful(
    workspace_id: str,
    brand_data: BrandSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """RESTful endpoint: Update brand voice via path parameter workspace_id."""
    data = await _update_brand_voice(
        db=db,
        brand_data=brand_data,
        workspace_identifier=workspace_id,
        user=user,
    )
    return success(data=data, message="Brand voice updated successfully")


@router.get(
    "/{workspace_id}/brand-voice", response_model=SuccessResponse[BrandVoiceWrapperResponse]
)
@db_transaction_handler("get brand voice", "Brand voice retrieved successfully")
@require_permissions("brand_voice.read", workspace_scoped=True)
async def get_brand_voice(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Retrieve brand voice for a workspace."""
    user_id = UUID(str(user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = BrandVoiceService(db)
    brand_voice = await service.get_brand_voice(
        workspace_id=workspace_uuid,
        user_id=user_id,
    )

    if not brand_voice:
        return success(
            data={"brand_voice": None},
            request=request,
            message="Brand voice not configured for this workspace",
        )

    return success(
        data={"brand_voice": _serialize_brand_voice(brand_voice)},
        request=request,
        message="Brand voice retrieved successfully",
    )


@router.delete(
    "/{workspace_id}/brand-voice", response_model=SuccessResponse[BrandVoiceStateResponse]
)
@db_transaction_handler("delete brand voice", "Brand voice deleted successfully")
@require_permissions("brand_voice.delete", workspace_scoped=True)
async def delete_brand_voice(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete brand voice for a workspace."""
    user_id = UUID(str(user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = BrandVoiceService(db)
    deleted = await service.delete_brand_voice(
        workspace_id=workspace_uuid,
        user_id=user_id,
    )

    if not deleted:
        return success(
            data={"deleted": False},
            request=request,
            message="No brand voice found to delete",
        )

    return success(
        data={"deleted": True},
        request=request,
        message="Brand voice deleted successfully",
    )


@router.post(
    "/{workspace_id}/brand-voice/refresh", response_model=SuccessResponse[BrandVoiceRefreshResponse]
)
@db_transaction_handler("refresh brand voice", "Brand voice refresh initiated", auto_commit=True)
@require_permissions("brand_voice.update", workspace_scoped=True)
async def refresh_brand_voice(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Trigger brand voice refresh via background pipeline and return operation ID."""
    user_id = UUID(str(user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = WorkspaceService(db)
    operation_id = await service.refresh_brand_voice_for_user(
        workspace_id=workspace_uuid,
        user_id=user_id,
    )

    return success(
        data={"operation_id": operation_id},
        request=request,
        message="Brand voice refresh initiated",
    )


__all__ = ["router"]
