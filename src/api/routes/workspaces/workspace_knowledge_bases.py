from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.knowledge_schema import (
    KnowledgeBaseCreateSchema,
    KnowledgeBaseUpdateSchema,
    KnowledgeBaseResponseSchema
)
from src.services.knowledge_base_service import KnowledgeBaseService
from src.utils.logger import logger
from src.utils.response_utils import success, created
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.kb_responses import (
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseDeleteResponse
)
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.dependencies.feature_gate import RequireFeature  # <-- added
from src.utils.workspace_utils import resolve_workspace_for_route

router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge-bases",
    tags=["knowledge-bases"],
)


@router.get("", response_model=SuccessResponse[KnowledgeBaseListResponse])
@db_transaction_handler("list knowledge bases", auto_commit=False)
async def list_knowledge_bases(
    workspace_id: str,
    request: Request,
    limit: int = 20,
    offset: int = 0,
    include_items_count: bool = True,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """List all knowledge bases for a workspace."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeBaseService(db)
    knowledge_bases, total_count = await service.list_knowledge_bases(
        workspace.id,
        include_items_count=include_items_count,
        limit=limit,
        offset=offset
    )

    return success(
        data={
            "knowledge_bases": knowledge_bases,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total_count,
        },
        request=request,
        message=f"Retrieved {len(knowledge_bases)} of {total_count} knowledge bases",
    )


@router.post(
    "",
    dependencies=[Depends(RequireFeature("knowledge_items"))],
    response_model=SuccessResponse[KnowledgeBaseResponse]
)
@db_transaction_handler("create knowledge base", "Knowledge base created successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def create_knowledge_base(
    workspace_id: str,
    request: Request,
    payload: KnowledgeBaseCreateSchema = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Create a new knowledge base."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeBaseService(db)
    knowledge_base = await service.create_knowledge_base(
        workspace.id,
        payload.name,
        payload.description
    )

    return created(
        data={"knowledge_base": knowledge_base.to_dict()},
        request=request,
        message="Knowledge base created successfully",
    )


@router.get("/{kb_id}", response_model=SuccessResponse[KnowledgeBaseResponse])
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("get knowledge base", auto_commit=False)
async def get_knowledge_base(
    workspace_id: str,
    kb_id: str,
    request: Request,
    include_items: bool = False,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Get a single knowledge base by ID."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeBaseService(db)
    knowledge_base = await service.get_knowledge_base(
        workspace.id,
        UUID(kb_id),
        include_items=include_items
    )

    return success(
        data={"knowledge_base": knowledge_base},
        request=request,
        message="Knowledge base retrieved successfully",
    )


@router.put(
    "/{kb_id}",
    dependencies=[Depends(RequireFeature("knowledge_items"))],
    response_model=SuccessResponse[KnowledgeBaseResponse]
)
@db_transaction_handler("update knowledge base", auto_commit=True)
@require_permissions("knowledge.update", workspace_scoped=True)
async def update_knowledge_base(
    workspace_id: str,
    kb_id: str,
    request: Request,
    payload: KnowledgeBaseUpdateSchema = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Update a knowledge base."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeBaseService(db)
    knowledge_base = await service.update_knowledge_base(
        workspace.id,
        UUID(kb_id),
        name=payload.name,
        description=payload.description
    )

    return success(
        data={"knowledge_base": knowledge_base},
        request=request,
        message="Knowledge base updated successfully",
    )


@router.delete(
    "/{kb_id}",
    dependencies=[Depends(RequireFeature("knowledge_items"))],
    response_model=SuccessResponse[KnowledgeBaseDeleteResponse]
)
@db_transaction_handler("delete knowledge base", "Knowledge base deleted successfully")
@require_permissions("knowledge.delete", workspace_scoped=True)
async def delete_knowledge_base(
    workspace_id: str,
    kb_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete a knowledge base and all its knowledge items."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeBaseService(db)
    await service.delete_knowledge_base(workspace.id, UUID(kb_id))

    return success(
        data={"kb_id": kb_id},
        request=request,
        message="Knowledge base deleted successfully",
    )
