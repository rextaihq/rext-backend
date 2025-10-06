from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.auth_utils import verify_current_user
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.schema.knowledge_schema import BrandSchema
from src.api.models.knowledge_models.knowledge_model import BrandVoice

router = APIRouter()


# -------------------------
# Update brand voice
# -------------------------
@router.put("/brand-voice")
@db_transaction_handler("update brand voice", "Brand voice updated successfully")
@require_permissions("workspace.update", workspace_scoped=True)
async def update_brand_voice(
    brand_data: BrandSchema,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Update brand voice for a workspace.

    Args:
        workspace_id: Workspace UUID or slug (query parameter)
        brand_data: Brand voice data

    Requires:
        - JWT authentication
        - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify user exists (using auth_utils)
    db_user = await verify_current_user(db, user_id)

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Get or create brand voice
    result = await db.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace.id))
    brand_voice = result.scalar_one_or_none()

    if brand_voice:
        # Update existing brand voice
        brand_voice.about = brand_data.about
        brand_voice.customer_profile = brand_data.customer_profile
        brand_voice.selling_position = brand_data.selling_position
        brand_voice.target_audience = brand_data.target_audience
        brand_voice.brand_voice = brand_data.brand_voice
        brand_voice.competitors = brand_data.competitors
        brand_voice.content_strategy = brand_data.content_pillar
    else:
        # Create new brand voice
        brand_voice = BrandVoice(
            workspace_id=workspace.id,
            about=brand_data.about,
            customer_profile=brand_data.customer_profile,
            selling_position=brand_data.selling_position,
            target_audience=brand_data.target_audience,
            brand_voice=brand_data.brand_voice,
            competitors=brand_data.competitors,
            content_strategy=brand_data.content_pillar,
        )
        db.add(brand_voice)

    await db.flush()
    await db.refresh(brand_voice)

    # Return raw data - decorator handles commit and success response
    return {
        "brand_voice": {
            "about": brand_voice.about,
            "customer_profile": brand_voice.customer_profile,
            "selling_position": brand_voice.selling_position,
            "target_audience": brand_voice.target_audience,
            "brand_voice": brand_voice.brand_voice,
            "competitors": brand_voice.competitors,
            "content_strategy": brand_voice.content_strategy,
        }
    }
