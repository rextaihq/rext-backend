from fastapi import (
    APIRouter, Depends, Request,
    HTTPException,
)
from src.utils.logger import logger
from src.utils.vector_store import add_to_vector_store, delete_vectors
from src.api.models.knowledge_models.knowledge_model import Website
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.schema.knowledge_schema import WebKnowledgeSchema
from src.api.security.dependencies import get_current_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.api.database.async_database import get_async_db
from src.utils.helper import web_page_scraper
from src.utils.response_utils import success, error, created
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)
from src.utils.db_utils import get_or_404
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter(
    prefix="/workspace/web_knowledge",
    tags=["WebKnowledge"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_status():
    return success(data={"status": "Web Knowledge Route is operational"})

# get web knowledges for a workspace
@router.get("/all")
@db_transaction_handler("get web knowledges", auto_commit=False)
async def get_web_knowledges(
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Get all web knowledge entries for a workspace.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Fetching web knowledges for workspace {workspace_id}")
    result = await db.execute(
        select(Website).where(Website.workspace_id == workspace_id)
    )
    web_knowledges = result.scalars().all()

    return {"web_knowledge": [knowledge.to_dict() for knowledge in web_knowledges]}
    

# Get knowledge by ID
@router.get("/{web_id}")
@db_transaction_handler("get web knowledge", auto_commit=False)
async def get_web_knowledge(
        web_id: str,
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Get a specific web knowledge entry by ID.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Fetching knowledge with ID: {web_id} for workspace {workspace_id}")
    knowledge = await get_or_404(db, Website, web_id, "web_knowledge")

    # Verify the knowledge belongs to the workspace
    if str(knowledge.workspace_id) != str(workspace_id):
        raise ResourceNotFoundException(f"Web knowledge {web_id} not found in workspace {workspace_id}")

    return {"web_knowledge": knowledge.to_dict()}
    
# Add new knowledge
@router.post("/add")
@db_transaction_handler("add web knowledge", "Web knowledge added and processed successfully")
@require_permissions("knowledge.create", workspace_scoped=True)
async def add_web_knowledge(
        data: WebKnowledgeSchema,
        request: Request,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
        """
        Add new web knowledge entry to a workspace.

        Requires:
        - JWT authentication
        - Workspace membership verification
        """
        user_id = user.get("identity")

        # Verify workspace access
        workspace, membership = await resolve_and_verify_workspace(db, data.workspace_id, UUID(user_id))

        logger.info(f"Adding web knowledge for workspace {data.workspace_id}")

        # check if the knowledge already exists
        result = await db.execute(select(Website).where(Website.url == str(data.url), Website.workspace_id == str(data.workspace_id)))
        existing_knowledge = result.scalar_one_or_none()
        if existing_knowledge:
            raise DuplicateResourceException(f"Knowledge for URL {data.url} already exists in the workspace")


        logger.info(f"Scraping content from URL: {data.url}")
        chunks, results = await web_page_scraper(urls=[data.url])
        result = results[0]
        if not result.success:
            logger.error(f"Failed to scrape URL: {str(data.url)}")
            raise WrextValidationException(
                message="Failed to scrape the provided URL",
                field_errors={"url": ["URL could not be scraped or is inaccessible"]}
            )

        logger.info(f"Building vector store for the scraped content")
        # Push scraped chunks into vector store
        logger.info(f"Saving knowledge entry to the database")
        new_knowledge = Website(
            workspace_id=data.workspace_id,
            url=result.url,
            status="trained",
            char_count=len(result.markdown),
            word_count=len(result.markdown.split()) if result else 0
        )
        db.add(new_knowledge)
        await db.flush()
        await db.refresh(new_knowledge)

        try:
            logger.info(f"Inserting {len(chunks)} chunks into vector store for {result.url}")
            success_status = add_to_vector_store(blog_context=chunks,
                                                 doc_id=f"{str(workspace.id)}_{str(new_knowledge.id)}")
            if not success_status:
                raise WrextExternalServiceException(
                    message="Failed to insert chunks into vector store",
                    service_name="vector_store",
                    service_error="Insertion returned False"
                )
        except Exception as vec_err:
            logger.exception("Vector store insertion failed")
            raise WrextExternalServiceException(
                message="Failed to process content in vector store",
                service_name="vector_store",
                service_error=str(vec_err)
            )

        knowledge_data = {
            "web_id": str(new_knowledge.id),
            "url": new_knowledge.url,
            "status": new_knowledge.status,
            "char_count": new_knowledge.char_count,
            "word_count": new_knowledge.word_count,
        }

        logger.info(f"Knowledge entry created with ID: {new_knowledge.id}")
        return created(
            data={"knowledge": knowledge_data},
            request=request,
            message="Web knowledge added and processed successfully"
        )


# Update web knowledge (title only, URL cannot be changed)
@router.put("/update/{web_id}")
@db_transaction_handler("update web knowledge", "Web knowledge updated successfully")
async def update_web_knowledge(
        web_id: str,
        title: str,
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Update web knowledge entry title.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Updating web knowledge ID: {web_id} in workspace: {workspace_id}")
    knowledge = await get_or_404(
        db,
        Website,
        web_id,
        "web_knowledge",
        additional_filters=[Website.workspace_id == workspace_id]
    )

    knowledge.title = title
    await db.flush()
    await db.refresh(knowledge)

    return {"web_knowledge": knowledge}


# Delete knowledge by ID
@router.delete("/delete/{web_id}")
@db_transaction_handler("delete web knowledge", "Knowledge deleted successfully")
@require_permissions("knowledge.delete", workspace_scoped=True)
async def delete_web_knowledge(
        web_id: str,
        request: Request,
        workspace_id: str,
        db: AsyncSession = Depends(get_async_db),
        user: dict = Depends(get_current_user)
):
    """
    Delete web knowledge entry from workspace.

    Requires:
    - JWT authentication
    - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    logger.info(f"Deleting knowledge with ID: {web_id} from workspace: {workspace_id}")
    knowledge = await get_or_404(
        db,
        Website,
        web_id,
        "web_knowledge",
        additional_filters=[Website.workspace_id == workspace_id]
    )

    # delete vector from store
    success_status = delete_vectors(vector_id=f"{str(workspace_id)}_{str(web_id)}")
    if not success_status:
        return error(
            message="Failed to delete vector store",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"workspace_id": workspace_id, "error_details": "Unable to delete vectors"},
            request=request
        )

    await db.delete(knowledge)
    logger.info(f"Knowledge with ID: {web_id} deleted successfully")
    return {}