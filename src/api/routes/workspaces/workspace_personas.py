"""Workspace personas management routes."""

from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.knowledge_models.persona_model import Persona
from src.api.schema.persona_schema import PersonaCreate, PersonaUpdate
from src.api.middleware.exceptions import ResourceNotFoundException
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.response_utils import success, created
from src.utils.workspace_utils import resolve_workspace_for_route
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.generic import GenericResponse
from src.api.schema.response.persona_responses import PersonaResponse, PersonaListResponse
from src.utils.logger import logger

router = APIRouter(tags=["workspace-personas"])


@router.get("/{workspace_id}/personas", response_model=SuccessResponse[PersonaListResponse])
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("get all workspace personas", auto_commit=False)
async def list_workspace_personas(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
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
    
    return success(
        data={
            "personas": [p.to_dict() for p in personas],
            "total_count": len(personas)
        },
        request=request,
        message="Workspace personas retrieved successfully"
    )


@router.get("/{workspace_id}/personas/{persona_id}", response_model=SuccessResponse[PersonaResponse])
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("get single persona", auto_commit=False)
async def get_persona(
    workspace_id: str,
    persona_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
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
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )
    
    return success(
        data=persona.to_dict(),
        request=request,
        message="Persona retrieved successfully"
    )


@router.post("/{workspace_id}/personas", status_code=status.HTTP_201_CREATED, response_model=SuccessResponse[PersonaResponse])
@require_permissions("workspace.create", workspace_scoped=True)
@db_transaction_handler("create persona", auto_commit=True)
async def create_persona(
    workspace_id: str,
    persona_data: PersonaCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
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
    
    return created(
        data=persona.to_dict(),
        request=request,
        message="Persona created successfully"
    )


@router.put("/{workspace_id}/personas/{persona_id}", response_model=SuccessResponse[PersonaResponse])
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("update persona", auto_commit=True)
async def update_persona(
    workspace_id: str,
    persona_id: str,
    persona_data: PersonaUpdate,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
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
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )
    
    # Update fields
    update_data = persona_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(persona, field, value)
    
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
    
    return success(
        data=persona.to_dict(),
        request=request,
        message="Persona updated successfully"
    )


@router.delete("/{workspace_id}/personas/{persona_id}", status_code=status.HTTP_200_OK, response_model=SuccessResponse[GenericResponse])
@require_permissions("workspace.delete", workspace_scoped=True)
@db_transaction_handler("delete persona", auto_commit=True)
async def delete_persona(
    workspace_id: str,
    persona_id: str,
    request: Request,
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
        raise ResourceNotFoundException(
            resource_type="persona",
            resource_id=persona_id,
        )
    
    await db.delete(persona)
    logger.info(
        "Deleted persona",
        extra={
            "workspace_id": str(workspace.id),
            "persona_id": str(persona.id),
        },
    )
    
    return success(request=request, message="Persona deleted successfully")


__all__ = ["router"]
