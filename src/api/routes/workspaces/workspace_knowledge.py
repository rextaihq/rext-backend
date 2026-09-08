from typing import Annotated, Any, Optional
from uuid import UUID
from src.utils.vector_store import search_vector_store
from src.utils.url_validator import SSRFValidationError
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Request, UploadFile
from pydantic import BaseModel, HttpUrl, constr
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextValidationException
from src.api.middleware.usage_limiter import check_knowledge_item_limit
from src.api.middleware.usage_limiter import check_embedding_rate_limit
from src.api.security.dependencies import get_current_user
from src.services.knowledge_service import KnowledgeService
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.knowledge_responses import (
    WorkspaceKnowledgeResponse,
    KnowledgeSearchResult,
    WebKnowledgeListResponse,
    WebKnowledgeResponse,
    WebKnowledgeDeleteResponse,
    FileKnowledgeListResponse,
    FileKnowledgeResponse,
    FileKnowledgeDeleteResponse,
    TextKnowledgeListResponse,
    TextKnowledgeResponse,
    TextKnowledgeDeleteResponse
)
from src.services.notification_helper import schedule_if_allowed
from src.utils.workspace_utils import resolve_workspace_for_route


class WebKnowledgeCreateRequest(BaseModel):
    """Payload for creating a web knowledge entry."""

    url: HttpUrl
    title: Optional[constr(strip_whitespace=True, min_length=1, max_length=255)] = None
    knowledge_base_id: Optional[UUID] = None


class WebKnowledgeUpdateRequest(BaseModel):
    """Payload for updating a web knowledge entry."""

    title: constr(strip_whitespace=True, min_length=1, max_length=255)


class TextKnowledgeCreateRequest(BaseModel):
    """Payload for creating a text knowledge entry."""

    title: constr(strip_whitespace=True, min_length=1, max_length=255)
    content: constr(strip_whitespace=True, min_length=10, max_length=5000)
    tags: Optional[list[constr(strip_whitespace=True, min_length=1, max_length=60)]] = None
    knowledge_base_id: Optional[UUID] = None


class TextKnowledgeUpdateRequest(BaseModel):
    """Payload for updating a text knowledge entry."""

    title: Optional[constr(strip_whitespace=True, min_length=1, max_length=255)] = None
    content: Optional[constr(strip_whitespace=True, min_length=10, max_length=5000)] = None
    tags: Optional[list[constr(strip_whitespace=True, min_length=1, max_length=60)]] = None


class FileKnowledgeUpdateRequest(BaseModel):
    """Payload for updating file knowledge metadata."""

    name: constr(strip_whitespace=True, min_length=1, max_length=255)

class KnowledgeSearchRequest(BaseModel):
    """Payload for searching knowledge via vector similarity."""

    query: constr(strip_whitespace=True, min_length=1, max_length=1000)
    knowledge_base_id: Optional[UUID] = None
    limit: int = 10
    score_threshold: Optional[float] = None

router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge",
    tags=["workspace-knowledge"],
)


@router.get("", response_model=SuccessResponse[WorkspaceKnowledgeResponse])
@db_transaction_handler("get workspace knowledge", auto_commit=False)
async def get_workspace_knowledge(
    workspace_id: str,
    request: Request,
    limit: int = 10,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return summary knowledge categories for a workspace (paginated)."""
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user,
    )

    service = KnowledgeService(db)
    web_items, web_total = await service.list_web_knowledge(workspace.id, limit=limit)
    file_items, file_total = await service.list_file_knowledge(workspace.id, limit=limit)
    text_items, text_total = await service.list_text_knowledge(workspace.id, limit=limit)

    return success(
        data={
            "web_knowledge": web_items,
            "file_knowledge": file_items,
            "text_knowledge": text_items,
            "summary": {
                "web_count": web_total,
                "file_count": file_total,
                "text_count": text_total,
                "total_count": web_total + file_total + text_total,
            },
        },
        request=request,
        message="Workspace knowledge retrieved successfully",
    )

@router.post("/search", response_model=SuccessResponse[KnowledgeSearchResult])
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("search knowledge", auto_commit=False)
async def search_knowledge(
    workspace_id: str,
    request: Request,
    payload: KnowledgeSearchRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Search knowledge base using vector similarity."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    from src.utils.vector_store import search_vector_store

    results = search_vector_store(
        query=payload.query,
        workspace_id=str(workspace.id),
        knowledge_base_id=str(payload.knowledge_base_id) if payload.knowledge_base_id else None,
        k=payload.limit,
        score_threshold=payload.score_threshold,
    )

    return success(
        data={
            "results": results,
            "query": payload.query,
            "total_results": len(results),
        },
        request=request,
        message="Knowledge search completed successfully",
    )


def _format_list_response(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Return consistent list response payloads."""
    return {key: items, "total_count": len(items)}


@router.get("/web", response_model=SuccessResponse[WebKnowledgeListResponse])
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("list web knowledge", auto_commit=False)
async def list_web_knowledge(
    workspace_id: str,
    request: Request,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return paginated web knowledge entries for a workspace."""
    workspace, _ = await resolve_workspace_for_route(
        db=db, workspace_identifier=workspace_id, user=user,
    )

    service = KnowledgeService(db)
    items, total_count = await service.list_web_knowledge(
        workspace.id, limit=limit, offset=offset
    )

    return success(
        data={
            "web_knowledge": items,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total_count,
        },
        request=request,
        message=f"Retrieved {len(items)} of {total_count} web knowledge entries",
    )


@router.post("/web", response_model=SuccessResponse[WebKnowledgeResponse])
@db_transaction_handler("create web knowledge", "Web knowledge created successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def create_web_knowledge(
    workspace_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: WebKnowledgeCreateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_knowledge_item_limit()),
    _rate: None = Depends(check_embedding_rate_limit()),  # ADD THIS
):
    """Create a new web knowledge entry by scraping a URL."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    raw_url = str(payload.url)
    if getattr(payload.url, "path", "/") == "/" and not getattr(payload.url, "query", "") and not getattr(payload.url, "fragment", ""):
        raw_url = raw_url.rstrip("/")
    try:
        knowledge = await service.add_web_knowledge(
            workspace.id,
            raw_url,
            knowledge_base_id=payload.knowledge_base_id,
        )
        # Update title if provided
        if payload.title:
            knowledge = await service.update_web_knowledge_title(
                workspace.id,
                UUID(str(knowledge["id"])),
                payload.title,
            )
        # Schedule success notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user["identity"]),
            background_tasks=background_tasks,
            pref_flag="kb_processing_completed",
            message=f"Web knowledge '{raw_url}' processed successfully.",
            payload={"knowledge_id": str(knowledge["id"]), "type": "web"},
            workspace_id=str(workspace.id),
        )
        return created(
            data={"web_knowledge": knowledge},
            request=request,
            message="Web knowledge added and processed successfully",
        )
    except SSRFValidationError as e:
        raise RextValidationException(
            message="The provided URL is not allowed",
            field_errors={"url": [str(e)]}
        )
        # Schedule failure notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user["identity"]),
            background_tasks=background_tasks,
            pref_flag="kb_processing_failed",
            message=f"Failed to create web knowledge for URL '{raw_url}'",
            payload={"url": raw_url, "type": "web"},
            workspace_id=str(workspace.id),
        )
        raise


@router.get("/web/{web_id}", response_model=SuccessResponse[WebKnowledgeResponse])
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("get web knowledge", auto_commit=False)
async def get_web_knowledge(
    workspace_id: str,
    web_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return a single web knowledge entry."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    knowledge = await service.get_web_knowledge(workspace.id, UUID(web_id))

    return success(
        data={"web_knowledge": knowledge},
        request=request,
        message="Web knowledge retrieved successfully",
    )


@router.patch("/web/{web_id}", response_model=SuccessResponse[WebKnowledgeResponse])
@require_permissions("knowledge.update", workspace_scoped=True)
@db_transaction_handler("update web knowledge", auto_commit=True)
async def update_web_knowledge(
    workspace_id: str,
    web_id: str,
    request: Request,
    payload: WebKnowledgeUpdateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Update metadata for an existing web knowledge entry."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    knowledge = await service.update_web_knowledge_title(
        workspace.id,
        UUID(web_id),
        payload.title,
    )

    return success(
        data={"web_knowledge": knowledge},
        request=request,
        message="Web knowledge updated successfully",
    )


@router.delete("/web/{web_id}", response_model=SuccessResponse[WebKnowledgeDeleteResponse])
@db_transaction_handler("delete web knowledge", "Web knowledge deleted successfully")
@require_permissions("knowledge.delete", workspace_scoped=True)
async def delete_web_knowledge(
    workspace_id: str,
    web_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete a web knowledge entry."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    await service.delete_web_knowledge(workspace.id, UUID(web_id))

    return success(
        data={"web_id": web_id},
        request=request,
        message="Web knowledge deleted successfully",
    )


@router.get("/files", response_model=SuccessResponse[FileKnowledgeListResponse])
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("list file knowledge", auto_commit=False)
async def list_file_knowledge(
    workspace_id: str,
    request: Request,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return all file knowledge entries for a workspace."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    items, total_count = await service.list_file_knowledge(workspace.id, limit=limit, offset=offset)

    return success(
        data={
            "file_knowledge": items,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total_count,
        },
        request=request,
        message=f"Retrieved {len(items)} of {total_count} file knowledge entries",
    )


@router.post("/files", response_model=SuccessResponse[FileKnowledgeResponse])
@db_transaction_handler("create file knowledge", "File knowledge uploaded successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def create_file_knowledge(
    workspace_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    _: None = Depends(check_knowledge_item_limit()),
    knowledge_base_id: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Upload a file and add it to workspace knowledge."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    # Parse knowledge_base_id if provided
    kb_id = UUID(knowledge_base_id) if knowledge_base_id else None

    service = KnowledgeService(db)
    knowledge = await service.add_file_knowledge(
        workspace.id,
        file,
        knowledge_base_id=kb_id,
        allowed_types=[
            # Documents
            "application/pdf",
            "text/plain",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            # Spreadsheets
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/csv",
            # Images
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
        ],
        max_size_mb=10,
    )

    try:
        # Schedule success notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user["identity"]),
            background_tasks=background_tasks,
            pref_flag="kb_processing_completed",
            message=f"File '{knowledge.file_name}' processed successfully.",
            payload={"knowledge_id": str(knowledge.id), "type": "file"},
            workspace_id=str(workspace.id),
        )
        return created(
            data={"file_knowledge": knowledge.to_dict()},
            request=request,
            message="File knowledge uploaded, processed, and stored successfully",
        )
    except Exception as e:
        await schedule_if_allowed(
            db=db,
            user_id=str(user["identity"]),
            background_tasks=background_tasks,
            pref_flag="kb_processing_failed",
            message=f"Failed to upload file knowledge",
            payload={"file_name": knowledge.file_name if 'knowledge' in locals() else None, "type": "file"},
            workspace_id=str(workspace.id),
        )
        raise


@router.get("/files/{file_id}", response_model=SuccessResponse[FileKnowledgeResponse])
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("get file knowledge", auto_commit=False)
async def get_file_knowledge(
    workspace_id: str,
    file_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return a single file knowledge entry."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    knowledge = await service.get_file_knowledge(workspace.id, UUID(file_id))

    return success(
        data={"file_knowledge": knowledge},
        request=request,
        message="File knowledge retrieved successfully",
    )


@router.patch("/files/{file_id}", response_model=SuccessResponse[FileKnowledgeResponse])
@require_permissions("knowledge.update", workspace_scoped=True)
@db_transaction_handler("update file knowledge", auto_commit=True)
async def update_file_knowledge(
    workspace_id: str,
    file_id: str,
    request: Request,
    payload: FileKnowledgeUpdateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Update metadata (name) for a file knowledge entry."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    knowledge = await service.update_file_knowledge_name(
        workspace.id,
        UUID(file_id),
        payload.name,
    )

    return success(
        data={"file_knowledge": knowledge},
        request=request,
        message="File knowledge updated successfully",
    )


@router.delete("/files/{file_id}", response_model=SuccessResponse[FileKnowledgeDeleteResponse])
@db_transaction_handler("delete file knowledge", "File knowledge deleted successfully")
@require_permissions("knowledge.delete", workspace_scoped=True)
async def delete_file_knowledge(
    workspace_id: str,
    file_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete a file knowledge entry and associated vector data."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    await service.delete_file_knowledge(
        UUID(file_id),
        workspace.id,
    )

    return success(
        data={"file_id": file_id},
        request=request,
        message="File knowledge deleted successfully",
    )


@router.get("/text", response_model=SuccessResponse[TextKnowledgeListResponse])
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("list text knowledge", auto_commit=False)
async def list_text_knowledge(
    workspace_id: str,
    request: Request,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return all text knowledge entries for a workspace."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    items, total_count = await service.list_text_knowledge(workspace.id, limit=limit, offset=offset)

    return success(
        data={
            "text_knowledge": items,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total_count,
        },
        request=request,
        message=f"Retrieved {len(items)} of {total_count} text knowledge entries",
    )


@router.post("/text", response_model=SuccessResponse[TextKnowledgeResponse])
@db_transaction_handler("create text knowledge", "Text knowledge created successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def create_text_knowledge(
    workspace_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: TextKnowledgeCreateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_knowledge_item_limit()),
):
    """Create a new text knowledge entry."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    knowledge = await service.add_text_knowledge(
        workspace.id,
        payload.title,
        payload.content,
        knowledge_base_id=payload.knowledge_base_id,
        tags=payload.tags,
    )


    try:
        # Schedule success notification
        await schedule_if_allowed(
            db=db,
            user_id=str(user["identity"]),
            background_tasks=background_tasks,
            pref_flag="kb_processing_completed",
            message=f"Text knowledge '{knowledge.title}' processed successfully.",
            payload={"knowledge_id": str(knowledge.id), "type": "text"},
            workspace_id=str(workspace.id),
        )
        return created(
            data={
                "text_knowledge": {
                    "text_id": str(knowledge.id),
                    "workspace_id": str(knowledge.workspace_id),
                    "title": knowledge.title,
                    "content": knowledge.content,
                }
            },
            request=request,
            message="Text knowledge added successfully",
        )
    except Exception as e:
        await schedule_if_allowed(
            db=db,
            user_id=str(user["identity"]),
            background_tasks=background_tasks,
            pref_flag="kb_processing_failed",
            message=f"Failed to create text knowledge",
            payload={"title": payload.title if payload else None, "type": "text"},
            workspace_id=str(workspace.id),
        )
        raise


@router.get("/text/{text_id}", response_model=SuccessResponse[TextKnowledgeResponse])
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("get text knowledge", auto_commit=False)
async def get_text_knowledge(
    workspace_id: str,
    text_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return a single text knowledge entry."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    knowledge = await service.get_text_knowledge(workspace.id, UUID(text_id))

    return success(
        data={"text_knowledge": knowledge},
        request=request,
        message="Text knowledge retrieved successfully",
    )


@router.patch("/text/{text_id}", response_model=SuccessResponse[TextKnowledgeResponse])
@require_permissions("knowledge.update", workspace_scoped=True)
@db_transaction_handler("update text knowledge", auto_commit=True)
async def update_text_knowledge(
    workspace_id: str,
    text_id: str,
    request: Request,
    payload: TextKnowledgeUpdateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Update title/content for a text knowledge entry."""
    if not any([payload.title, payload.content, payload.tags]):
        raise RextValidationException(
            message="At least one field (title, content, tags) must be provided",
            field_errors={"payload": ["No fields supplied for update"]},
        )

    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    knowledge = await service.update_text_knowledge(
        UUID(text_id),
        workspace.id,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
    )

    return success(
        data={"text_knowledge": knowledge},
        request=request,
        message="Text knowledge updated successfully",
    )


@router.delete("/text/{text_id}", response_model=SuccessResponse[TextKnowledgeDeleteResponse])
@db_transaction_handler("delete text knowledge", "Text knowledge deleted successfully")
@require_permissions("knowledge.delete", workspace_scoped=True)
async def delete_text_knowledge(
    workspace_id: str,
    text_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Delete a text knowledge entry."""
    workspace, _ = await resolve_workspace_for_route(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    await service.delete_text_knowledge(
        UUID(text_id),
        workspace.id,
    )

    return success(
        data={"text_id": text_id},
        request=request,
        message="Text knowledge deleted successfully",
    )
