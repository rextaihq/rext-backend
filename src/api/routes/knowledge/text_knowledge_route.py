from fastapi import (
    APIRouter, Depends, Request,
    HTTPException
)
from src.utils.logger import logger
from src.api.models.knowledge_models.knowledge_model import TextKnowledge
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.schema.knowledge_schema import TextKnowledgeSchema
from src.utils.response_utils import success
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.security.dependencies import get_current_user
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    WrextAuthenticationException,
    ResourceNotFoundException
)
from src.utils.db_utils import get_or_404
from src.api.routes.content.modules.helpers import verify_workspace_access

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
    workspace, membership = await verify_workspace_access(db, workspace_id, user_id)

    try:
        logger.info(f"Fetching text knowledges for workspace {workspace_id}")
        result = await db.execute(
            select(TextKnowledge).where(TextKnowledge.workspace_id == workspace_id)
        )
        text_knowledges = result.scalars().all()
        return success(
            data={"text_knowledge": [knowledge.to_dict() for knowledge in text_knowledges]},
            request=request
        )
    except Exception as e:
        logger.error(f"Error fetching text knowledges: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
# get text knowledge by ID
@router.get("/{text_id}")
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
    workspace, membership = await verify_workspace_access(db, workspace_id, user_id)

    try:
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

        return success(
            data={"text_knowledge": knowledge.to_dict()},
            request=request
        )
    except ResourceNotFoundException as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching text knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Create text knowledge
@router.post("/add-text")
async def text_knowledge(
    payload: TextKnowledgeSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Add new text knowledge entry to a workspace.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await verify_workspace_access(db, payload.workspace_id, user_id)

    try:
        logger.info(f"Adding text knowledge for workspace {payload.workspace_id}")

        # add the text content in the
        new_knowledge = TextKnowledge(
            workspace_id=payload.workspace_id,
            content=payload.content
        )

        db.add(new_knowledge)
        await db.commit()
        await db.refresh(new_knowledge)

        logger.info(f"New text knowledge created in workspace {payload.workspace_id}")

        # make a success response
        text_response = {
            "text_id":str(new_knowledge.id),
            "worspace_id":str(new_knowledge.workspace_id),
            "message":"text Knowledge add successfull"
        } 
        return success(
            data=text_response,
            request=request,
            message="Text knowledge created successfully"
        )
    except Exception as e:
        logger.error(f"Error uploading file knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Update text knowledge
@router.put("/update/{text_id}")
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
    workspace, membership = await verify_workspace_access(db, workspace_id, user_id)

    try:
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

        await db.commit()
        await db.refresh(text_knowledge)

        return success(
            data={"text_knowledge": text_knowledge.to_dict()},
            request=request,
            message="Text knowledge updated successfully"
        )
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error updating text knowledge: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")


# Delete text knowledge
@router.delete("/delete/{text_id}")
async def delete_text_knowledge(
    text_id: str,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Delete text knowledge entry from workspace.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await verify_workspace_access(db, workspace_id, user_id)

    try:
        logger.info(f"Deleting text knowledge with ID: {text_id} from workspace: {workspace_id}")
        text_knowledge = await get_or_404(
            db,
            TextKnowledge,
            text_id,
            "text_knowledge",
            additional_filters=[TextKnowledge.workspace_id == workspace_id]
        )

        await db.delete(text_knowledge)
        await db.commit()

        return success(
            data={"text_id": text_id},
            request=request,
            message="Text knowledge deleted successfully"
        )
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error deleting text knowledge: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")