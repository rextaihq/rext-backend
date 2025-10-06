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
from src.utils.file_upload_utils import validate_and_store_file, delete_file
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
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.api.middleware.exceptions import WrextValidationException, DuplicateResourceException


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
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

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
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

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
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Adding file knowledge for workspace {workspace_id}")

    # 2. Validate and store file securely
    file_metadata = await validate_and_store_file(
        file=file,
        workspace_id=str(workspace.id),
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
            "image/webp"
        ],
        max_size_mb=10,
        enable_virus_scan=False  # Set to True if ClamAV installed
    )

    # 3. Check for duplicate by hash
    result = await db.execute(select(KnowledgeFiles).where(
        KnowledgeFiles.file_hash == file_metadata["hash"],
        KnowledgeFiles.workspace_id == workspace_id
    ))
    existing_knowledge = result.scalar_one_or_none()
    if existing_knowledge:
        # Delete uploaded file (duplicate)
        await delete_file(file_metadata["secure_path"])
        raise DuplicateResourceException(
            resource="file_knowledge",
            identifier=file.filename,
            message=f"File already exists in knowledge base (duplicate content detected)"
        )

    # 4. Extract text from file
    chunks = load_split_file_data(file_metadata["secure_path"])

    if len(chunks) == 0:
        raise WrextValidationException(
            message="Failed to extract content from the file",
            field_errors={"file": ["No content could be extracted from file"]}
        )

    # 5. Save metadata in DB
    new_knowledge = KnowledgeFiles(
        workspace_id=workspace_id,
        file_name=file_metadata["safe_filename"],
        file_type=file_metadata["mime_type"],
        file_size=file_metadata["size"],
        file_path=file_metadata["secure_path"],
        file_hash=file_metadata["hash"],
        mime_type=file_metadata["mime_type"],
        chunk_count=len(chunks)
    )
    db.add(new_knowledge)
    await db.flush()
    await db.refresh(new_knowledge)

    # 6. Add to vector store
    try:
        logger.info(f"Inserting {len(chunks)} chunks into vector store for {file_metadata['secure_path']}")
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

    # 7. Response
    return {"file_knowledge": new_knowledge.to_dict()}


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
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

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
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Deleting file knowledge with ID: {file_id} from workspace: {workspace_id}")
    knowledge = await get_or_404(
        db,
        KnowledgeFiles,
        file_id,
        "file_knowledge",
        additional_filters=[KnowledgeFiles.workspace_id == workspace_id]
    )

    # Delete from vector store
    success_status = delete_vectors(vector_id=f"{str(workspace_id)}_{str(file_id)}")
    if not success_status:
        logger.warning(f"Failed to delete vectors for file {file_id}")

    # Delete the physical file from storage
    if knowledge.file_path:
        file_deleted = await delete_file(knowledge.file_path)
        if file_deleted:
            logger.info(f"Deleted file at path: {knowledge.file_path}")
        else:
            logger.warning(f"File at path {knowledge.file_path} does not exist or could not be deleted")

    await db.delete(knowledge)
    logger.info(f"File knowledge with ID: {file_id} deleted successfully")
    return {"file_id": file_id}