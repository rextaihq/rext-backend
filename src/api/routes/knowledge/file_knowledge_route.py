from fastapi import (
    APIRouter, Depends, Request,
    HTTPException,
    UploadFile, File
)
from src.utils.logger import logger
from src.api.models.knowledge_models.knowledge_model import KnowledgeFiles
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.utils.vector_store import add_to_vector_store, delete_vectors
from src.utils.utils import load_split_file_data
from src.utils.response_utils import success, error
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.security.auth import get_api_key, API_KEY
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from pathlib import Path
import os
from src.api.middleware.exceptions import (
    WrextExternalServiceException,
    WrextAuthenticationException
)


# for file storage
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


router = APIRouter(
    prefix="/workspace/file",
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

# Get all file knowledges
@router.get("/all")
def get_file_knowledges(
        request: Request,
        db: Session = Depends(get_db),
        api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info("Fetching all file knowledges")
        file_knowledges = db.query(KnowledgeFiles).all()
        return success(data=[knowledge.to_dict() for knowledge in file_knowledges])
    except Exception as e:
        logger.error(f"Error fetching knowledges: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
# get file knowledge by ID
@router.get("/{file_id}")
def get_file_knowledge(
        file_id: str,
        request: Request,
        db: Session = Depends(get_db),
        api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info(f"Fetching file knowledge with ID: {file_id}")
        knowledge = db.query(KnowledgeFiles).filter(KnowledgeFiles.id == file_id).first()
        if not knowledge:
            raise HTTPException(status_code=404, detail=f"File Knowledge with ID {file_id} not found")
        return success(data=knowledge.to_dict())
    except HTTPException as e:
        logger.warning(str(e))
        raise e
    except Exception as e:
        logger.error(f"Error fetching file knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    

# Add new file knowledge
@router.post("/add")
async def add_file_knowledge(
        request: Request,
        file: UploadFile = File(...),
        db: Session = Depends(get_db),
        workspace_id: str = None,
        api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        # 1. Validate workspace
        workspace = db.query(WorkspaceModel).filter(WorkspaceModel.id == workspace_id).first()
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace with ID {workspace_id} not found")

        # 2. Check duplicate
        existing_knowledge = db.query(KnowledgeFiles).filter(
            KnowledgeFiles.file_name == file.filename,
            KnowledgeFiles.workspace_id == workspace_id
        ).first()
        if existing_knowledge:
            raise HTTPException(
                status_code=400,
                detail=f"File Knowledge for file {file.filename} already exists in the workspace"
            )

        # 3. Save file locally
        file_path = UPLOAD_DIR / f"{workspace_id}_{file.filename}"
        with open(file_path, "wb") as f:
            f.write(await file.read())

        # Save metadata in DB
        file_size = os.path.getsize(file_path)
        new_knowledge = KnowledgeFiles(
            workspace_id=workspace_id,
            file_name=file.filename,
            file_type=file.content_type,
                file_size=file_size,
            file_path=str(file_path),
        )
        db.add(new_knowledge)
        db.commit()
        db.refresh(new_knowledge)

        # 4. Extract text from file
        chunks = load_split_file_data(str(file_path))

        if len(chunks) == 0:
            raise HTTPException(status_code=400, detail="Failed to extract content from the file")

        # 5. Add to vector store
        try:
            logger.info(f"Inserting {len(chunks)} chunks into vector store for {file_path}")
            success_status = add_to_vector_store(blog_context=chunks, doc_id=f"{str(workspace.id)}_{str(new_knowledge.id)}")
            if not success_status:
                raise WrextExternalServiceException(
                    message="Failed to insert chunks into vector store",
                    service_name="vector_store",
                    service_error="Insertion returned False"
                )
        except Exception as e:
            logger.error(f"Error building vector store: {e}")
            raise HTTPException(status_code=500, detail="Failed to build vector store from file content")

        # file data = 
        file_data = {
            "id": str(new_knowledge.id),
            "workspace_id": str(new_knowledge.workspace_id),
            "file_name": new_knowledge.file_name,
            "file_type": new_knowledge.file_type,
            "file_size": new_knowledge.file_size,
            "file_path": new_knowledge.file_path,
        }

        # 7. Response
        return success(
            data=file_data,
            request=request,
            message="File Knowledge uploaded, processed, and stored successfully"
        )

    except HTTPException as e:
        logger.warning(str(e))
        raise e
    except Exception as e:
        logger.error(f"Error adding file knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
# Delete file knowledge
@router.delete("/delete/{workspace_id}/{file_id}")
def delete_file_knowledge(
        file_id: str,
        workspace_id:str,
        request: Request,
        db: Session = Depends(get_db),
        api_key: str = Depends(get_api_key)
):
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        logger.info(f"Deleting file knowledge with ID: {file_id}")
        knowledge = db.query(KnowledgeFiles).filter(KnowledgeFiles.id == file_id, KnowledgeFiles.workspace_id == workspace_id).first()

        if not knowledge:
            raise HTTPException(status_code=404, detail=f"File Knowledge with ID {file_id} not found")
        
        # Delete the associated file from storage
        if os.path.exists(knowledge.file_path):
            os.remove(knowledge.file_path)
            logger.info(f"Deleted file at path: {knowledge.file_path}")

            # delete vector from store
            success_status = delete_vectors(vector_id=f"{str(workspace_id)}_{str(file_id)}")
            if not success_status:
                return error(
                    message="Failed to delete vector store",
                    code=ErrorCode.INTERNAL_SERVER_ERROR,
                    status_code=500,
                    severity=ErrorSeverity.HIGH,
                    context={"workspace_id": workspace_id, "error_details": "Unable to delete vectors"},
                    request=request
                )

        else:
            logger.warning(f"File at path {knowledge.file_path} does not exist")

        db.delete(knowledge)
        db.commit()
        logger.info(f"File knowledge with ID: {file_id} deleted successfully")
        return success(data={"file_id": file_id}, message="File Knowledge deleted successfully", request=request)
    except HTTPException as e:
        logger.warning(str(e))
        raise e
    except Exception as e:
        logger.error(f"Error deleting file knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")