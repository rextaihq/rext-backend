from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.knowledge_models.persona_model import Persona
from src.api.schema.persona_schema import PersonaCreate, PersonaUpdate, PersonaResponse
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_workspace_for_route
from src.services.workspace_permission_service import WorkspacePermissionService
from src.utils.rbac_utils import get_user_permissions, get_user_roles
from src.utils.response_utils import success
from src.utils.workspace_utils import async_get_workspace_id_from_identifier
from src.utils.logger import logger
from src.utils.route_decorators import require_permissions

router = APIRouter(tags=["Workspace Permissions"])


@router.get("/{workspace_id}/permissions/me")
@require_permissions("member.read", workspace_scoped=True)
async def get_my_workspace_permissions(
    workspace_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Get all personas for a workspace.
    
    Personas are extracted from website content during workspace creation
    or can be created manually.
    """
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
    # Fetch personas
    result = await db.execute(
        select(Persona)
        .where(Persona.workspace_id == workspace.id)
        .order_by(Persona.created_at.desc())
    )
    personas = result.scalars().all()
    
    return {
        "personas": [p.to_dict() for p in personas],
        "total_count": len(personas)
    }


@router.get("/{workspace_id}/personas/{persona_id}")
@db_transaction_handler("get single persona", auto_commit=False)
@require_permissions("workspace.read", workspace_scoped=True)
async def get_persona(
    workspace_id: str,
    persona_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Get a single persona by ID."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
    # Fetch persona
    result = await db.execute(
        select(Persona).where(
            Persona.id == UUID(persona_id),
            Persona.workspace_id == workspace.id
        )
    )
    persona = result.scalar_one_or_none()
    
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found"
        )
    
    return persona.to_dict()


@router.post("/{workspace_id}/personas", status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create persona", auto_commit=True)
@require_permissions("workspace.create", workspace_scoped=True)
async def create_persona(
    workspace_id: str,
    permission: str,
    user: dict = Depends(get_current_user),
):
    """Create a new persona manually."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
    # Create persona
    persona = Persona(
        workspace_id=workspace.id,
        name=persona_data.name,
        description=persona_data.description,
        full_name=persona_data.full_name,
        professional_title=persona_data.professional_title,
        areas_of_expertise=persona_data.areas_of_expertise,
        tone_of_voice=persona_data.tone_of_voice,
        bio=persona_data.bio,
        linkedin_url=persona_data.linkedin_url,
        demographics=persona_data.demographics,
        pain_points=persona_data.pain_points,
        goals=persona_data.goals,
        behaviors=persona_data.behaviors,
    )
    
    db.add(persona)
    await db.flush()
    await db.refresh(persona)
    
    logger.info(
        "Created persona",
        extra={
            "workspace_id": str(workspace.id),
            "persona_id": str(persona.id),
        },
    )
    
    return persona.to_dict()


@router.put("/{workspace_id}/personas/{persona_id}")
@db_transaction_handler("update persona", auto_commit=True)
@require_permissions("workspace.update", workspace_scoped=True)
async def update_persona(
    workspace_id: str,
    persona_id: str,
    persona_data: PersonaUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Update an existing persona."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
    # Fetch persona
    result = await db.execute(
        select(Persona).where(
            Persona.id == UUID(persona_id),
            Persona.workspace_id == workspace.id
        )
    )
    persona = result.scalar_one_or_none()
    
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found"
        )
    
    # Update fields
    update_data = persona_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(persona, field, value)
    
    from datetime import timezone
    persona.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(persona)
    
    logger.info(
        "Updated persona",
        extra={
            "workspace_id": str(workspace.id),
            "persona_id": str(persona.id),
        },
    )
    
    return persona.to_dict()


@router.post("/{workspace_id}/permissions/refresh")
@require_permissions("member.read", workspace_scoped=True)
async def refresh_workspace_permissions(
    workspace_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete a persona."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)
    
    # Fetch persona
    result = await db.execute(
        select(Persona).where(
            Persona.id == UUID(persona_id),
            Persona.workspace_id == workspace.id
        )
    )
    persona = result.scalar_one_or_none()
    
    if not persona:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Persona not found"
        )
    
    await db.delete(persona)
    logger.info(
        "Deleted persona",
        extra={
            "workspace_id": str(workspace.id),
            "persona_id": str(persona.id),
        },
    )
    
    return None


__all__ = ["router"]
