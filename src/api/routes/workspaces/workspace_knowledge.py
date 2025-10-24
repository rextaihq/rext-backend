from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Request, UploadFile
from pydantic import BaseModel, HttpUrl, constr
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import WrextValidationException
from src.api.middleware.usage_limiter import check_knowledge_item_limit
from src.api.security.dependencies import get_current_user
from src.services.knowledge_service import KnowledgeService
from src.utils.auth_utils import verify_current_user
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace


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


router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge",
    tags=["workspace-knowledge"],
)


@router.get("")
@db_transaction_handler("get workspace knowledge", auto_commit=False)
async def get_workspace_knowledge(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return all knowledge categories for a workspace."""
    workspace, _ = await _resolve_workspace(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    web_knowledge = await service.list_web_knowledge(workspace.id)
    file_knowledge = await service.list_file_knowledge(workspace.id)
    text_knowledge = await service.list_text_knowledge(workspace.id)

    summary = {
        "web_count": len(web_knowledge),
        "file_count": len(file_knowledge),
        "text_count": len(text_knowledge),
        "total_count": len(web_knowledge) + len(file_knowledge) + len(text_knowledge),
    }

    return success(
        data={
            "web_knowledge": web_knowledge,
            "file_knowledge": file_knowledge,
            "text_knowledge": text_knowledge,
            "summary": summary,
        },
        request=request,
        message="Workspace knowledge retrieved successfully",
    )


async def _resolve_workspace(
    *,
    db: AsyncSession,
    workspace_identifier: str,
    user: dict[str, Any],
) -> tuple[Any, Any]:
    """Resolve workspace and ensure the current user has access."""
    user_id = user.get("identity")
    await verify_current_user(db, user_id)
    return await resolve_and_verify_workspace(db, workspace_identifier, UUID(str(user_id)))


def _format_list_response(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Return consistent list response payloads."""
    return {key: items, "total_count": len(items)}


@router.get("/web")
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("list web knowledge", auto_commit=False)
async def list_web_knowledge(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return all web knowledge entries for a workspace."""
    workspace, _ = await _resolve_workspace(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    knowledge = await service.list_web_knowledge(workspace.id)
    payload = _format_list_response(knowledge, "web_knowledge")

    return success(
        data=payload,
        request=request,
        message=f"Retrieved {payload['total_count']} web knowledge entr{'y' if payload['total_count'] == 1 else 'ies'}",
    )


@router.post("/web")
@db_transaction_handler("create web knowledge", "Web knowledge created successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def create_web_knowledge(
    workspace_id: str,
    request: Request,
    payload: WebKnowledgeCreateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_knowledge_item_limit()),
):
    """Create a new web knowledge entry by scraping a URL."""
    workspace, _ = await _resolve_workspace(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    raw_url = str(payload.url)
    if getattr(payload.url, "path", "/") == "/" and not getattr(payload.url, "query", "") and not getattr(payload.url, "fragment", ""):
        raw_url = raw_url.rstrip("/")

    knowledge = await service.add_web_knowledge(
        workspace.id,
        raw_url,
        knowledge_base_id=payload.knowledge_base_id
    )

    # Update title if provided
    if payload.title:
        knowledge = await service.update_web_knowledge_title(workspace.id, UUID(str(knowledge["id"])), payload.title)

    return created(
        data={"web_knowledge": knowledge},
        request=request,
        message="Web knowledge added and processed successfully",
    )


@router.get("/web/{web_id}")
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
    workspace, _ = await _resolve_workspace(
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


@router.patch("/web/{web_id}")
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
    workspace, _ = await _resolve_workspace(
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


@router.delete("/web/{web_id}")
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
    workspace, _ = await _resolve_workspace(
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


@router.get("/files")
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("list file knowledge", auto_commit=False)
async def list_file_knowledge(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return all file knowledge entries for a workspace."""
    workspace, _ = await _resolve_workspace(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    file_knowledge = await service.list_file_knowledge(workspace.id)
    payload = _format_list_response(file_knowledge, "file_knowledge")

    return success(
        data=payload,
        request=request,
        message=f"Retrieved {payload['total_count']} file knowledge entr{'y' if payload['total_count'] == 1 else 'ies'}",
    )


@router.post("/files")
@db_transaction_handler("create file knowledge", "File knowledge uploaded successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def create_file_knowledge(
    workspace_id: str,
    request: Request,
    file: Annotated[UploadFile, File(...)],
    _: None = Depends(check_knowledge_item_limit()),
    knowledge_base_id: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Upload a file and add it to workspace knowledge."""
    workspace, _ = await _resolve_workspace(
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

    return created(
        data={"file_knowledge": knowledge.to_dict()},
        request=request,
        message="File knowledge uploaded, processed, and stored successfully",
    )


@router.get("/files/{file_id}")
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
    workspace, _ = await _resolve_workspace(
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


@router.patch("/files/{file_id}")
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
    workspace, _ = await _resolve_workspace(
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


@router.delete("/files/{file_id}")
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
    workspace, _ = await _resolve_workspace(
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


@router.get("/text")
@require_permissions("knowledge.read", workspace_scoped=True)
@db_transaction_handler("list text knowledge", auto_commit=False)
async def list_text_knowledge(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """Return all text knowledge entries for a workspace."""
    workspace, _ = await _resolve_workspace(
        db=db,
        workspace_identifier=workspace_id,
        user=user,
    )

    service = KnowledgeService(db)
    text_knowledge = await service.list_text_knowledge(workspace.id)
    payload = _format_list_response(text_knowledge, "text_knowledge")

    return success(
        data=payload,
        request=request,
        message=f"Retrieved {payload['total_count']} text knowledge entr{'y' if payload['total_count'] == 1 else 'ies'}",
    )


@router.post("/text")
@db_transaction_handler("create text knowledge", "Text knowledge created successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def create_text_knowledge(
    workspace_id: str,
    request: Request,
    payload: TextKnowledgeCreateRequest = Body(...),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
    _: None = Depends(check_knowledge_item_limit()),
):
    """Create a new text knowledge entry."""
    workspace, _ = await _resolve_workspace(
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
    )

    if payload.tags:
        logger.warning("Tags provided for text knowledge are currently ignored", extra={"tags": payload.tags})

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


@router.get("/text/{text_id}")
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
    workspace, _ = await _resolve_workspace(
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


@router.patch("/text/{text_id}")
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
        raise WrextValidationException(
            message="At least one field (title, content, tags) must be provided",
            field_errors={"payload": ["No fields supplied for update"]},
        )

    workspace, _ = await _resolve_workspace(
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
    )

    if payload.tags:
        logger.warning("Tags update for text knowledge is not yet supported", extra={"tags": payload.tags})

    return success(
        data={"text_knowledge": knowledge},
        request=request,
        message="Text knowledge updated successfully",
    )


@router.delete("/text/{text_id}")
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
    workspace, _ = await _resolve_workspace(
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
