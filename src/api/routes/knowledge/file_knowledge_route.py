from fastapi import (
    APIRouter, Depends, Request,
    HTTPException,
    UploadFile, File
)
from src.utils.logger import logger
from src.api.models.knowledge_model import KnowledgeFiles
from src.api.models.workspace_model import WorkspaceModel
from src.nodes.vectorStore.buildVectorStore import build_vector_store
from src.utils.utils import load_split_file_data
from src.utils.response_utils import success
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from pathlib import Path
import os


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
def get_file_knowledges(request: Request, db: Session = Depends(get_db)):
    try:
        logger.info("Fetching all file knowledges")
        file_knowledges = db.query(KnowledgeFiles).all()
        return success(data=[knowledge.to_dict() for knowledge in file_knowledges])
    except Exception as e:
        logger.error(f"Error fetching knowledges: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
# get file knowledge by ID
@router.get("/{file_id}")
def get_file_knowledge(file_id: str, request: Request, db: Session = Depends(get_db)):
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
    ):
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

        # 4. Extract text from file
        chunks = load_split_file_data(str(file_path))

        if len(chunks) == 0:
            raise HTTPException(status_code=400, detail="Failed to extract content from the file")

        # 5. Add to vector store
        try: 
            build_vector_store(
                blog_context=chunks,
                vector_store_path="my_faiss_index"
            )
        except Exception as e:
            logger.error(f"Error building vector store: {e}")
            raise HTTPException(status_code=500, detail="Failed to build vector store from file content")

        # 6. Save metadata in DB
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
@router.delete("/delete/{file_id}")
def delete_file_knowledge(file_id: str, request: Request, db: Session = Depends(get_db)):
    try:
        logger.info(f"Deleting file knowledge with ID: {file_id}")
        knowledge = db.query(KnowledgeFiles).filter(KnowledgeFiles.id == file_id).first()
        if not knowledge:
            raise HTTPException(status_code=404, detail=f"File Knowledge with ID {file_id} not found")
        
        # Delete the associated file from storage
        if os.path.exists(knowledge.file_path):
            os.remove(knowledge.file_path)
            logger.info(f"Deleted file at path: {knowledge.file_path}")
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