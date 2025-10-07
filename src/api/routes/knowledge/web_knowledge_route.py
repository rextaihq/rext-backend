
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.knowledge_schema import WebKnowledgeSchema
from src.api.security.dependencies import get_current_user
from src.services.knowledge_service import KnowledgeService
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(
    prefix="/workspace/web_knowledge",
    tags=["WebKnowledge"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_status():
    return success(data={"status": "Web Knowledge Route is operational"})


@router.get("/all")
@db_transaction_handler("get web knowledges", auto_commit=False)
async def get_web_knowledges(
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    workspace_uuid = UUID(workspace_id)
    await resolve_and_verify_workspace(db, workspace_uuid, UUID(str(user.get("identity"))))

    service = KnowledgeService(db)
    knowledge = await service.list_web_knowledge(workspace_uuid)

    return success(
        data={"web_knowledge": knowledge},
        request=request,
        message=f"Retrieved {len(knowledge)} web knowledge entr{'y' if len(knowledge)==1 else 'ies'}",
    )


@router.get("/{web_id}", response_model=dict)
@db_transaction_handler("get web knowledge", auto_commit=False)
async def get_web_knowledge(
    web_id: str,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    workspace_uuid = UUID(workspace_id)
    await resolve_and_verify_workspace(db, workspace_uuid, UUID(str(user.get("identity"))))

    service = KnowledgeService(db)
    knowledge = await service.get_web_knowledge(workspace_uuid, UUID(web_id))

    return success(
        data={"web_knowledge": knowledge},
        request=request,
        message="Web knowledge retrieved successfully",
    )


@router.post("/add")
@db_transaction_handler("add web knowledge", "Web knowledge added and processed successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def add_web_knowledge(
    data: WebKnowledgeSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    workspace_uuid = data.workspace_id
    await resolve_and_verify_workspace(db, workspace_uuid, UUID(str(user.get("identity"))))

    service = KnowledgeService(db)
    knowledge = await service.add_web_knowledge(workspace_uuid, str(data.url))

    return created(
        data={"knowledge": knowledge},
        request=request,
        message="Web knowledge added and processed successfully",
    )


@router.put("/update/{web_id}")
@db_transaction_handler("update web knowledge", "Web knowledge updated successfully")
async def update_web_knowledge(
    web_id: str,
    title: str,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    workspace_uuid = UUID(workspace_id)
    await resolve_and_verify_workspace(db, workspace_uuid, UUID(str(user.get("identity"))))

    service = KnowledgeService(db)
    knowledge = await service.update_web_knowledge_title(workspace_uuid, UUID(web_id), title)

    return success(
        data={"web_knowledge": knowledge},
        request=request,
        message="Web knowledge updated successfully",
    )


@router.delete("/delete/{web_id}")
@db_transaction_handler("delete web knowledge", "Knowledge deleted successfully")
@require_permissions("knowledge.delete", workspace_scoped=True)
async def delete_web_knowledge(
    web_id: str,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    workspace_uuid = UUID(workspace_id)
    await resolve_and_verify_workspace(db, workspace_uuid, UUID(str(user.get("identity"))))

    service = KnowledgeService(db)
    await service.delete_web_knowledge(workspace_uuid, UUID(web_id))

    return success(
        data={},
        request=request,
        message="Knowledge deleted successfully",
    )
