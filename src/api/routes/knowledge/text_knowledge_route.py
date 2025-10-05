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
from src.api.security.auth import get_api_key, API_KEY
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    WrextAuthenticationException,
    ResourceNotFoundException
)
from src.utils.db_utils import get_or_404

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

# Get text knowledges
@router.get("/all")
async def get_file_knowledges(
        request: Request,
        db: AsyncSession = Depends(get_async_db),
        api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info("Fetching all file knowledges")
        result = await db.execute(select(TextKnowledge))
        file_knowledges = result.scalars().all()
        return success(data=[knowledge.to_dict() for knowledge in file_knowledges])
    except Exception as e:
        logger.error(f"Error fetching knowledges: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
# get file knowledge by ID
@router.get("/{workspace_id}/{text_id}")
async def get_file_knowledge(
        text_id: str,
        workspace_id:str,
        db: AsyncSession = Depends(get_async_db),
        api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info(f"Fetching file knowledge with ID: {text_id}")
        knowledge = await get_or_404(
            db,
            TextKnowledge,
            text_id,
            "text_knowledge",
            additional_filters=[TextKnowledge.workspace_id == workspace_id]
        )
        return success(data=knowledge.to_dict())
    except ResourceNotFoundException as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching file knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Create text knowledge not file
@router.post("/add-text")
async def text_knowledge(
    payload:TextKnowledgeSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        # 1. Validate workspace
        workspace = await get_or_404(db, WorkspaceModel, payload.workspace_id, "workspace")

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
@router.put("/update/{workspace_id}/{text_id}")
async def update_text_knowledge(
    text_id: str,
    workspace_id:str,
    new_content: str,
    request: Request = None,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info(f"Updating text knowledge with ID: {text_id}")
        text_knowledge = await get_or_404(
            db,
            TextKnowledge,
            text_id,
            "text_knowledge",
            additional_filters=[TextKnowledge.workspace_id == workspace_id]
        )

        # Update fields
        if new_content:
            text_knowledge.content = new_content
        if workspace_id:
            text_knowledge.workspace_id = workspace_id
        if text_id:
            text_knowledge.id = text_id


        await db.commit()
        await db.refresh(text_knowledge)

        # make a success response
        text_response = {
            "text_id":str(text_knowledge.id),
            "worspace_id":str(text_knowledge.workspace_id),
            "message":"text Knowledge add successful"
        } 
        return success(
            data=text_response,
            request=request,
            message="Text knowledge updated successfully"
        )
    except Exception as e:
        logger.error(f"Error updating text knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# Delete text knowledge
@router.delete("/delete/{workspace_id}/{text_id}")
async def delete_text_knowledge(
    text_id: str,
    workspace_id:str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info(f"Deleting text knowledge with ID: {text_id}")
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
            data={"deleted_id": text_id},
            request=request,
            message="Text knowledge deleted successfully"
        )
    except Exception as e:
        logger.error(f"Error deleting text knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")