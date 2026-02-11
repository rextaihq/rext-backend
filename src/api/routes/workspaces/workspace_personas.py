from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.knowledge_models.persona_model import Persona
from src.api.schema.persona_schema import PersonaCreate, PersonaUpdate, PersonaResponse
from src.utils.auth_utils import verify_current_user
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.utils.logger import logger

router = APIRouter(tags=["workspace-personas"])


@router.get("/{workspace_id}/personas")
@db_transaction_handler("get workspace personas", auto_commit=False)
@require_permissions("workspace.read", workspace_scoped=True)
async def get_workspace_personas(
    workspace_id: str,
    request: Request,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Get all personas for a workspace.
    
    Personas are extracted from website content during workspace creation
    or can be created manually.
    """
    user_id = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_id))
    
    # Verify workspace access
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, user_id)
    
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
    user_id = UUID(str(user.get("identity") ))
    await verify_current_user(db, str(user_id))
    
    # Verify workspace access
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, user_id)
    
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
    persona_data: PersonaCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Create a new persona manually."""
    user_id = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_id))
    
    # Verify workspace access
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, user_id)
    
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
    
    logger.info(f"Created persona {persona.id} for workspace {workspace.id}")
    
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
    user_id = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_id))
    
    # Verify workspace access
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, user_id)
    
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
    
    logger.info(f"Updated persona {persona.id}")
    
    return persona.to_dict()


@router.delete("/{workspace_id}/personas/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
@db_transaction_handler("delete persona", auto_commit=True)
@require_permissions("workspace.delete", workspace_scoped=True)
async def delete_persona(
    workspace_id: str,
    persona_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete a persona."""
    user_id = UUID(str(user.get("identity")))
    await verify_current_user(db, str(user_id))
    
    # Verify workspace access
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, user_id)
    
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
    logger.info(f"Deleted persona {persona.id}")
    
    return None


__all__ = ["router"]
