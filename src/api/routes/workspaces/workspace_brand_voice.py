from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.schema.knowledge_schema import BrandSchema
from src.api.security.dependencies import get_current_user
from src.services.brand_voice_service import BrandVoiceService
from src.utils.auth_utils import verify_current_user
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(tags=["workspace-brand-voice"])


def _serialize_brand_voice(brand_voice) -> dict:
    """Serialize BrandVoice ORM model into API response payload."""
    return {
        "id": str(brand_voice.id) if getattr(brand_voice, "id", None) else None,
        "workspace_id": str(brand_voice.workspace_id),
        "about": brand_voice.about,
        "customer_profile": brand_voice.customer_profile,
        "selling_position": brand_voice.selling_position,
        "target_audience": brand_voice.target_audience or [],
        "brand_voice": brand_voice.brand_voice or [],
        "competitors": brand_voice.competitors or [],
        "content_strategy": brand_voice.content_strategy or [],
        "created_at": brand_voice.created_at.isoformat() if getattr(brand_voice, "created_at", None) else None,
        "updated_at": brand_voice.updated_at.isoformat() if getattr(brand_voice, "updated_at", None) else None,
    }


async def _update_brand_voice(
    *,
    db: AsyncSession,
    brand_data: BrandSchema,
    workspace_identifier: str,
    user: dict,
) -> dict:
    """Shared handler logic for brand voice upsert operations."""
    user_id = UUID(str(user.get("identity")))

    # Verify user exists (using auth_utils)
    await verify_current_user(db, str(user_id))

    # Resolve workspace identifier to UUID and ensure membership
    workspace, _membership = await resolve_and_verify_workspace(db, workspace_identifier, user_id)

    service = BrandVoiceService(db)
    brand_voice = await service.upsert_brand_voice(
        workspace_id=workspace.id,
        user_id=user_id,
        brand_data=brand_data,
    )

    return {"brand_voice": _serialize_brand_voice(brand_voice)}


@router.put("/{workspace_id}/brand-voice")
@db_transaction_handler("update brand voice", "Brand voice updated successfully")
@require_permissions("workspace.update", workspace_scoped=True)
async def update_brand_voice_restful(
    workspace_id: str,
    brand_data: BrandSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """RESTful endpoint: Update brand voice via path parameter workspace_id."""
    return await _update_brand_voice(
        db=db,
        brand_data=brand_data,
        workspace_identifier=workspace_id,
        user=user,
    )
__all__ = ["router"]
