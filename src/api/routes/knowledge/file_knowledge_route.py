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
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.security.dependencies import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.database.async_database import get_async_db
from pathlib import Path
import os
from src.api.middleware.exceptions import (
    WrextExternalServiceException,
    WrextAuthenticationException,
    ResourceNotFoundException
)
from src.utils.db_utils import get_or_404
from src.api.routes.content.modules.helpers import verify_workspace_access


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
async def get_status(request: Request):
    logger.info("File Knowledge Route health check called.")
    return success(
        data={"status": "operational", "service": "file_knowledge_service"},
        request=request,
        message="File Knowledge Route is working!"
    )

# Get all file knowledges for a workspace
@router.get("/all")
@db_transaction_handler("get file knowledges", auto_commit=False)
async def get_file_knowledges(
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Get all file knowledge entries for a workspace.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await verify_workspace_access(db, workspace_id, user_id)

    logger.info(f"Fetching file knowledges for workspace {workspace_id}")
    result = await db.execute(
        select(KnowledgeFiles).where(KnowledgeFiles.workspace_id == workspace_id)
    )
    file_knowledges = result.scalars().all()

    # Return raw data - decorator handles success response
    return {"file_knowledge": [knowledge.to_dict() for knowledge in file_knowledges]}
    
# get file knowledge by ID
@router.get("/{file_id}")
@db_transaction_handler("get file knowledge", auto_commit=False)
async def get_file_knowledge(
        file_id: str,
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Get a specific file knowledge entry by ID.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await verify_workspace_access(db, workspace_id, user_id)

    logger.info(f"Fetching file knowledge with ID: {file_id} for workspace {workspace_id}")
    knowledge = await get_or_404(db, KnowledgeFiles, file_id, "file_knowledge")

    # Verify the knowledge belongs to the workspace
    if str(knowledge.workspace_id) != str(workspace_id):
        raise ResourceNotFoundException(f"File knowledge {file_id} not found in workspace {workspace_id}")

    return {"file_knowledge": knowledge.to_dict()}
    

# Add new file knowledge
@router.post("/add")
@db_transaction_handler("add file knowledge", "File Knowledge uploaded, processed, and stored successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def add_file_knowledge(
        request: Request,
        workspace_id: str,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Add new file knowledge entry to a workspace.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await verify_workspace_access(db, workspace_id, user_id)

    logger.info(f"Adding file knowledge for workspace {workspace_id}")

    # 2. Check duplicate
    result = await db.execute(select(KnowledgeFiles).where(
        KnowledgeFiles.file_name == file.filename,
        KnowledgeFiles.workspace_id == workspace_id
    ))
    existing_knowledge = result.scalar_one_or_none()
    if existing_knowledge:
        raise DuplicateResourceException(
            resource="file_knowledge",
            identifier=file.filename,
            message=f"File Knowledge for file {file.filename} already exists in the workspace"
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
    await db.flush()
    await db.refresh(new_knowledge)

    # 4. Extract text from file
    chunks = load_split_file_data(str(file_path))

    if len(chunks) == 0:
        raise WrextValidationException(
            message="Failed to extract content from the file",
            field_errors={"file": ["No content could be extracted from file"]}
        )

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
    except WrextExternalServiceException:
        raise
    except Exception as e:
        logger.error(f"Error building vector store: {e}")
        raise WrextExternalServiceException(
            message="Failed to build vector store from file content",
            service_name="vector_store",
            service_error=str(e)
        )

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
    return file_data


# Update file knowledge (name only)
@router.put("/update/{file_id}")
@db_transaction_handler("update file knowledge", "File knowledge updated successfully")
async def update_file_knowledge(
        file_id: str,
        name: str,
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Update file knowledge entry name.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await verify_workspace_access(db, workspace_id, user_id)

    logger.info(f"Updating file knowledge ID: {file_id} in workspace: {workspace_id}")
    knowledge = await get_or_404(
        db,
        KnowledgeFiles,
        file_id,
        "file_knowledge",
        additional_filters=[KnowledgeFiles.workspace_id == workspace_id]
    )

    knowledge.name = name
    await db.flush()
    await db.refresh(knowledge)

    return {"file_knowledge": knowledge}


# Delete file knowledge
@router.delete("/delete/{file_id}")
@db_transaction_handler("delete file knowledge", "File Knowledge deleted successfully")
@require_permissions("knowledge.delete", workspace_scoped=True)
async def delete_file_knowledge(
        file_id: str,
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Delete file knowledge entry from workspace.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await verify_workspace_access(db, workspace_id, user_id)

    logger.info(f"Deleting file knowledge with ID: {file_id} from workspace: {workspace_id}")
    knowledge = await get_or_404(
        db,
        KnowledgeFiles,
        file_id,
        "file_knowledge",
        additional_filters=[KnowledgeFiles.workspace_id == workspace_id]
    )

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

    await db.delete(knowledge)
    logger.info(f"File knowledge with ID: {file_id} deleted successfully")
    return {"file_id": file_id}