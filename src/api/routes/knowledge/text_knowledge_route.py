from fastapi import (
    APIRouter, Depends, Request,
    HTTPException
)
from src.utils.logger import logger
from src.api.models.knowledge_model import TextKnowledge
from src.api.models.workspace_model import WorkspaceModel
from src.api.schema.knowledge_schema import TextKnowledgeSchema
from src.utils.response_utils import success
from sqlalchemy.orm import Session
from src.api.database.database import get_db

router = APIRouter(
    prefix="/workspace/text",
    tags=["file_knowledge"],
    responses={404: {"description": "Not found"}},
)


# Health Check
@router.get("/")
def get_status(request: Request):
    logger.info("File Knowledge Route health check called.")
    return success(
        data={"status": "operational", "service": "file_knowledge_service"},
        request=request,
        message="File Knowledge Route is working!"
    )

# Get text knowledges
@router.get("/all")
def get_file_knowledges(request: Request, db: Session = Depends(get_db)):
    try:
        logger.info("Fetching all file knowledges")
        file_knowledges = db.query(TextKnowledge).all()
        return success(data=[knowledge.to_dict() for knowledge in file_knowledges])
    except Exception as e:
        logger.error(f"Error fetching knowledges: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
# get file knowledge by ID
@router.get("/{workspace_id}/{text_id}")
def get_file_knowledge(
        text_id: str,
        workspace_id:str,
        db: Session = Depends(get_db)
):
    try:
        logger.info(f"Fetching file knowledge with ID: {text_id}")
        knowledge = db.query(TextKnowledge).filter(TextKnowledge.id == text_id,
                                                   workspace_id==workspace_id).first()
        if not knowledge:
            raise HTTPException(status_code=404, detail=f"File Knowledge with ID {text_id} not found")
        return success(data=knowledge.to_dict())
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error fetching file knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Create text knowledge not file
@router.post("/add-text")
def text_knowledge(
    payload:TextKnowledgeSchema,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        # 1. Validate workspace
        workspace = db.query(WorkspaceModel).filter(WorkspaceModel.id == payload.workspace_id).first()
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace with ID {payload.workspace_id} not found")

        # add the text content in the
        new_knowledge = TextKnowledge(
            workspace_id=payload.workspace_id,
            content=payload.content
        )

        db.add(new_knowledge)
        db.commit()
        db.refresh(new_knowledge)

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
def update_text_knowledge(
    text_id: str,
    workspace_id:str,
    new_content: str,
    request: Request = None,
    db: Session = Depends(get_db),
):
    try:
        logger.info(f"Updating text knowledge with ID: {text_id}")
        text_knowledge = db.query(TextKnowledge).filter(TextKnowledge.id == text_id,workspace_id==workspace_id).first()
        if not text_knowledge:
            raise HTTPException(status_code=404, detail=f"Text Knowledge with ID {text_id} not found")

        # Update fields
        if new_content:
            text_knowledge.content = new_content
        if workspace_id:
            text_knowledge.workspace_id = workspace_id
        if text_id:
            text_knowledge.id = text_id


        db.commit()
        db.refresh(text_knowledge)

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
def delete_text_knowledge(
    text_id: str,
    workspace_id:str,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        logger.info(f"Deleting text knowledge with ID: {text_id}")
        text_knowledge = db.query(TextKnowledge).filter(TextKnowledge.id == text_id,workspace_id==workspace_id).first()
        if not text_knowledge:
            raise HTTPException(status_code=404, detail=f"Text Knowledge with ID {text_id} not found")

        db.delete(text_knowledge)
        db.commit()

        return success(
            data={"deleted_id": text_id},
            request=request,
            message="Text knowledge deleted successfully"
        )
    except Exception as e:
        logger.error(f"Error deleting text knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")