from fastapi import (
    APIRouter, Depends, Request,
    HTTPException
)
from uuid import UUID
from src.utils.logger import logger
from src.api.models.knowledge_models.knowledge_model import TextKnowledge
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.schema.knowledge_schema import TextKnowledgeSchema
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.security.dependencies import get_current_user
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    WrextAuthenticationException,
    ResourceNotFoundException
)
from src.utils.db_utils import get_or_404
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.services.knowledge_service import KnowledgeService

router = APIRouter(
    prefix="/workspace/text",
    tags=["file_knowledge"],
    responses={404: {"description": "Not found"}},
)


# Health Check
@router.get("/")
async def get_status(request: Request):
    logger.info("File Knowledge Route health check called.")
    return success(
        data={"status": "operational", "service": "file_knowledge_service"},
        request=request,
        message="File Knowledge Route is working!"
    )

# Get text knowledges for a workspace
@router.get("/all")
@db_transaction_handler("get text knowledges", auto_commit=False)
async def get_text_knowledges(
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Get all text knowledge entries for a workspace.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Fetching text knowledges for workspace {workspace_id}")
    result = await db.execute(
        select(TextKnowledge).where(TextKnowledge.workspace_id == workspace_id)
    )
    text_knowledges = result.scalars().all()

    return {"text_knowledge": [knowledge.to_dict() for knowledge in text_knowledges]}
    
# get text knowledge by ID
@router.get("/{text_id}")
@db_transaction_handler("get text knowledge", auto_commit=False)
async def get_text_knowledge(
        text_id: str,
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Get a specific text knowledge entry by ID.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Fetching text knowledge with ID: {text_id} for workspace {workspace_id}")
    knowledge = await get_or_404(
        db,
        TextKnowledge,
        text_id,
        "text_knowledge",
        additional_filters=[TextKnowledge.workspace_id == workspace_id]
    )

    # Verify the knowledge belongs to the workspace
    if str(knowledge.workspace_id) != str(workspace_id):
        raise ResourceNotFoundException(f"Text knowledge {text_id} not found in workspace {workspace_id}")

    return {"text_knowledge": knowledge.to_dict()}

# Create text knowledge
@router.post("/add-text")
@db_transaction_handler("add text knowledge", "Text knowledge added successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def text_knowledge(
    payload: TextKnowledgeSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Add new text knowledge entry to a workspace - Thin controller using KnowledgeService.

    Requires:
    - JWT authentication
    - Workspace membership verification
    - knowledge.create permission
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, payload.workspace_id, UUID(user_id))

    logger.info(f"Adding text knowledge for workspace {payload.workspace_id}")

    # Use service for business logic
    service = KnowledgeService(db)
    new_knowledge = await service.add_text_knowledge(
        workspace_id=UUID(payload.workspace_id),
        title=payload.title if hasattr(payload, 'title') else "Untitled",
        content=payload.content
    )

    # Return raw data - decorator handles success response
    return {
        "text_knowledge": {
            "text_id": str(new_knowledge.id),
            "workspace_id": str(new_knowledge.workspace_id),
            "title": new_knowledge.title,
            "content": new_knowledge.content
        }
    }

# Update text knowledge
@router.put("/update/{text_id}")
@db_transaction_handler("update text knowledge", auto_commit=True)
async def update_text_knowledge(
    text_id: str,
    new_content: str,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Update text knowledge entry content.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Updating text knowledge with ID: {text_id} in workspace: {workspace_id}")
    text_knowledge = await get_or_404(
        db,
        TextKnowledge,
        text_id,
        "text_knowledge",
        additional_filters=[TextKnowledge.workspace_id == workspace_id]
    )

    # Update content
    text_knowledge.content = new_content

    await db.flush()
    await db.refresh(text_knowledge)

    return {"text_knowledge": text_knowledge.to_dict()}


# Delete text knowledge
@router.delete("/delete/{text_id}")
@db_transaction_handler("delete text knowledge", "Text knowledge deleted successfully")
@require_permissions("knowledge.delete", workspace_scoped=True)
async def delete_text_knowledge(
    text_id: str,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Delete text knowledge entry from workspace - Thin controller using KnowledgeService.

    Requires:
    - JWT authentication
    - Workspace membership verification
    - knowledge.delete permission
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Deleting text knowledge with ID: {text_id} from workspace: {workspace_id}")

    # Use service for business logic
    service = KnowledgeService(db)
    await service.delete_text_knowledge(
        text_id=UUID(text_id),
        workspace_id=UUID(workspace_id)
    )

    # Return raw data - decorator handles success response
    return {"text_id": text_id}