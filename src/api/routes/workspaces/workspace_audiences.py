"""Workspace audience (buyer/reader persona segment) management routes."""

from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.knowledge_models.audience_model import Audience
from src.api.schema.audience_schema import (
    AudienceCreate,
    AudienceUpdate,
    AudienceResponse,
    AudienceListResponse,
)
from src.api.middleware.exceptions import ResourceNotFoundException
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.response_utils import success, created
from src.utils.workspace_utils import resolve_workspace_for_route
from src.api.schema.response_schemas import SuccessResponse, GenericResponse
from src.utils.logger import logger

router = APIRouter(tags=["workspace-audiences"])


@router.get("/{workspace_id}/audiences", response_model=SuccessResponse[AudienceListResponse])
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("get all workspace audiences", auto_commit=False)
async def list_workspace_audiences(
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Get all audience segments for a workspace."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)

    result = await db.execute(
        select(Audience)
        .where(Audience.workspace_id == workspace.id)
        .order_by(Audience.created_at.desc())
    )
    audiences = result.scalars().all()

    return success(
        data={
            "audiences": [a.to_dict() for a in audiences],
            "total_count": len(audiences)
        },
        request=request,
        message="Workspace audiences retrieved successfully"
    )


@router.get("/{workspace_id}/audiences/{audience_id}", response_model=SuccessResponse[AudienceResponse])
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("get single audience", auto_commit=False)
async def get_audience(
    workspace_id: str,
    audience_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Get a single audience segment by ID."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)

    result = await db.execute(
        select(Audience).where(
            Audience.id == UUID(audience_id),
            Audience.workspace_id == workspace.id
        )
    )
    audience = result.scalar_one_or_none()

    if not audience:
        raise ResourceNotFoundException(resource_type="audience", resource_id=audience_id)

    return success(data=audience.to_dict(), request=request, message="Audience retrieved successfully")


@router.post("/{workspace_id}/audiences", status_code=status.HTTP_201_CREATED, response_model=SuccessResponse[AudienceResponse])
@require_permissions("workspace.create", workspace_scoped=True)
@db_transaction_handler("create audience", auto_commit=True)
async def create_audience(
    workspace_id: str,
    audience_data: AudienceCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Create a new audience segment manually."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)

    audience = Audience(
        workspace_id=workspace.id,
        name=audience_data.name,
        description=audience_data.description,
        demographics=audience_data.demographics.model_dump() if audience_data.demographics else None,
        psychographics=audience_data.psychographics.model_dump() if audience_data.psychographics else None,
        pain_points=audience_data.pain_points,
        goals=audience_data.goals,
        behaviors=audience_data.behaviors,
        objections=audience_data.objections,
        preferred_channels=audience_data.preferred_channels,
        buying_stage=audience_data.buying_stage,
    )

    db.add(audience)
    await db.flush()
    await db.refresh(audience)

    logger.info(
        "Created audience",
        extra={"workspace_id": str(workspace.id), "audience_id": str(audience.id)},
    )

    return created(data=audience.to_dict(), request=request, message="Audience created successfully")


@router.put("/{workspace_id}/audiences/{audience_id}", response_model=SuccessResponse[AudienceResponse])
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("update audience", auto_commit=True)
async def update_audience(
    workspace_id: str,
    audience_id: str,
    audience_data: AudienceUpdate,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    request: Request = None,
):
    """Update an existing audience segment."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)

    result = await db.execute(
        select(Audience).where(
            Audience.id == UUID(audience_id),
            Audience.workspace_id == workspace.id
        )
    )
    audience = result.scalar_one_or_none()

    if not audience:
        raise ResourceNotFoundException(resource_type="audience", resource_id=audience_id)

    update_data = audience_data.model_dump(exclude_unset=True)
    for field in ("demographics", "psychographics"):
        if field in update_data and update_data[field] is not None:
            update_data[field] = update_data[field]

    for field, value in update_data.items():
        setattr(audience, field, value)

    audience.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(audience)

    logger.info(
        "Updated audience",
        extra={"workspace_id": str(workspace.id), "audience_id": str(audience.id)},
    )

    return success(data=audience.to_dict(), request=request, message="Audience updated successfully")


@router.delete("/{workspace_id}/audiences/{audience_id}", status_code=status.HTTP_200_OK, response_model=SuccessResponse[GenericResponse])
@require_permissions("workspace.delete", workspace_scoped=True)
@db_transaction_handler("delete audience", auto_commit=True)
async def delete_audience(
    workspace_id: str,
    audience_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete an audience segment."""
    workspace, _ = await resolve_workspace_for_route(db=db, workspace_identifier=workspace_id, user=user)

    result = await db.execute(
        select(Audience).where(
            Audience.id == UUID(audience_id),
            Audience.workspace_id == workspace.id
        )
    )
    audience = result.scalar_one_or_none()

    if not audience:
        raise ResourceNotFoundException(resource_type="audience", resource_id=audience_id)

    await db.delete(audience)
    logger.info(
        "Deleted audience",
        extra={"workspace_id": str(workspace.id), "audience_id": str(audience.id)},
    )

    return success(data={}, request=request, message="Audience deleted successfully")


__all__ = ["router"]
