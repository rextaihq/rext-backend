from fastapi import (
    APIRouter, Depends, Request,
)
from src.utils.logger import logger
from src.api.schema.workspace_schema import WorkspaceSchema
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.utils.vector_store import add_to_vector_store,delete_vectors
from src.api.models.knowledge_model import BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.model.model import load_model
from sqlalchemy.orm import Session
from src.api.security.auth import get_api_key, API_KEY
from src.api.database.database import get_db
from src.utils.helper import web_page_scraper
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)
from datetime import datetime, timezone


router = APIRouter(
    prefix="/workspace",
    tags=["workspace"],
    responses={404: {"description": "Not found"}},
)


# Health Check
@router.get("/")
def get_status(request: Request):
    logger.info("Workspace Route health check called.")
    return success(
        data={"status": "operational", "service": "workspace_service"},
        request=request,
        message="Workspace service is working!"
    )


# get workspaces
@router.get("/all")
def get_workspaces(
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
        workspaces = db.query(WorkspaceModel).all()
        workspace_data = [
            {
                "id": str(ws.id),
                "title": ws.title,
                "description": ws.description,
                "url": ws.url,
                "created_at": ws.created_at.isoformat() if hasattr(ws, 'created_at') else None
            } for ws in workspaces
        ]

        return success(
            data={
                "workspaces": workspace_data,
                "total_count": len(workspace_data)
            },
            request=request,
            message=f"Retrieved {len(workspace_data)} workspaces successfully"
        )
    except Exception as e:
        logger.exception("Error fetching workspaces")
        return error(
            message="Failed to retrieve workspaces",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

# get by id
@router.get("/{workspace_id}")
def get_workspace_by_id(
    workspace_id: str,
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
        workspace = db.query(WorkspaceModel).filter_by(id=workspace_id).first()
        if not workspace:
            logger.warning(f"Workspace not found: {workspace_id}")
            raise ResourceNotFoundException(
                resource_type="workspace",
                resource_id=workspace_id
            )

        workspace_data = {
            "id": str(workspace.id),
            "title": workspace.title,
            "description": workspace.description,
            "url": workspace.url,
            "created_at": workspace.created_at.isoformat() if hasattr(workspace, 'created_at') else None
        }

        return success(
            data={"workspace": workspace_data},
            request=request,
            message="Workspace retrieved successfully"
        )
    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace {workspace_id}")
        return error(
            message="Failed to retrieve workspace",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )

# CREATE Workspace
@router.post("/create")
async def create_workspace(
    data: WorkspaceSchema,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)

):
    logger.info(f"Received request to create workspace: {data.title}")
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        # Check duplicate
        existing_workspace = db.query(WorkspaceModel).filter_by(title=data.title).first()
        if existing_workspace:
            logger.warning(f"Duplicate workspace title: {data.title}")
            raise DuplicateResourceException(
                message=f"Workspace with title '{data.title}' already exists",
                resource_type="workspace",
                conflicting_field="title",
                conflicting_value=data.title
            )

        # Scrape website
        logger.info(f"Scraping content from: {data.url}")
        chunks, results = await web_page_scraper(urls=[data.url])
        result = results[0]
        if not result.success:
            logger.error(f"Failed to scrape URL: {data.url}")
            raise WrextValidationException(
                message="Failed to scrape the provided URL",
                field_errors={"url": ["URL could not be scraped or is inaccessible"]}
            )

        content = result.markdown

        # Create workspace record first
        workspace = WorkspaceModel(
            title=data.title,
            description=getattr(data, "description", None),
            url=str(data.url),
            created_at=datetime.now(timezone.utc)
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        logger.info(f"Workspace created with id={workspace.id}")

        # Push scraped chunks into vector store
        try:
            logger.info(f"Inserting {len(chunks)} chunks into vector store for {result.url}")
            success_status = add_to_vector_store(blog_context=chunks, doc_id=str(workspace.id))
            if not success_status:
                raise WrextExternalServiceException(
                    message="Failed to insert chunks into vector store",
                    service_name="vector_store",
                    service_error="Insertion returned False"
                )

        except Exception as vec_err:
            logger.exception("Vector store insertion failed")
            # Continue workflow – don't block workspace creation
            raise WrextExternalServiceException(
                message="Failed to process content in vector store",
                service_name="vector_store",
                service_error=str(vec_err)
            )

        # Extract brand info using LLM
        try:
            logger.info("Extracting brand voice using LLM")
            model = load_model()
            structure_model = model.with_structured_output(BrandSchema)
            brand_data = structure_model.invoke(content)
            logger.info(f"Brand data extracted: {brand_data}")

            brand_voice = BrandVoice(
                workspace_id=workspace.id,
                about=brand_data.about,
                customer_profile=brand_data.customer_profile,
                selling_position=brand_data.selling_position,
                target_audience=brand_data.target_audience,
                brand_voice=brand_data.brand_voice,
                competitors=brand_data.competitors,
                content_strategy=brand_data.content_pillar,
            )

            db.add(brand_voice)
            db.commit()
            db.refresh(brand_voice)

            logger.info(f"Brand voice saved for workspace {workspace.id}")
        except Exception as llm_err:
            logger.exception("LLM extraction failed")
            # Workspace is still valid – don't fail entire request
            raise WrextExternalServiceException(
                message="Failed to extract brand voice using AI",
                service_name="llm_service",
                service_error=str(llm_err)
            )

        workspace_data = {
            "id": str(workspace.id),
            "title": workspace.title,
            "description": workspace.description,
            "url": workspace.url,
            # "created_at": workspace.created_at.isoformat() if workspace.created_at else None
        }

        return created(
            data={"workspace": workspace_data},
            request=request,
            message="Workspace created successfully"
        )

    except (DuplicateResourceException, WrextValidationException, WrextExternalServiceException):
        # Re-raise custom exceptions to be handled by middleware
        raise
    except Exception as e:
        logger.exception(f"Unexpected error creating workspace {data.title}")
        db.rollback()
        return error(
            message="Failed to create workspace due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


# Delete
@router.delete("/delete/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    logger.info(f"Received request to delete workspace: {workspace_id}")
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        workspace = db.query(WorkspaceModel).filter_by(id=workspace_id).first()
        if not workspace:
            logger.warning(f"Workspace not found: {workspace_id}")
            raise ResourceNotFoundException(
                resource_type="workspace",
                resource_id=workspace_id
            )
        # delete vector from store
        success_status = delete_vectors(vector_id=str(workspace_id))
        if not success_status:
            return error(
                message="Failed to delete vector store",
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                status_code=500,
                severity=ErrorSeverity.HIGH,
                context={"workspace_id": workspace_id, "error_details": "Unable to delete vectors"},
                request=request
            )

        # Delete the workspace
        db.delete(workspace)
        db.commit()
        logger.info(f"Workspace deleted: {workspace_id}")

        # return no_content(request=request)
        return success(
            data={},
            request=request,
            message="Workspace deleted successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting workspace {workspace_id}")
        db.rollback()
        return error(
            message="Failed to delete workspace",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"workspace_id": workspace_id, "error_details": str(e)},
            request=request
        )


# update
@router.put("/update/{workspace_id}")
def update_workspace(
    workspace_id: str,
    data: WorkspaceSchema,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    logger.info(f"Received request to update workspace: {workspace_id}")
    if api_key != API_KEY:
        raise WrextAuthenticationException(
            message="Invalid API key provided",
            context={"api_key_provided": bool(api_key)}
        )
    try:
        workspace = db.query(WorkspaceModel).filter_by(id=workspace_id).first()
        if not workspace:
            logger.warning(f"Workspace not found: {workspace_id}")
            raise ResourceNotFoundException(
                resource_type="workspace",
                resource_id=workspace_id
            )

        # Check for duplicate title if title is being updated
        if data.title and data.title != workspace.title:
            existing_workspace = db.query(WorkspaceModel).filter_by(title=data.title).first()
            if existing_workspace:
                logger.warning(f"Duplicate workspace title: {data.title}")
                raise DuplicateResourceException(
                    message=f"Workspace with title '{data.title}' already exists",
                    resource_type="workspace",
                    conflicting_field="title",
                    conflicting_value=data.title
                )

        # Update fields
        if data.title:
            workspace.title = data.title
        if data.description is not None:
            workspace.description = data.description
        if data.url:
            workspace.url = str(data.url)

        db.commit()
        db.refresh(workspace)
        logger.info(f"Workspace updated: {workspace_id}")

        workspace_data = {
            "id": str(workspace.id),
            "title": workspace.title,
            "description": workspace.description,
            "url": workspace.url,
            # "updated_at": workspace.updated_at.isoformat() if hasattr(workspace, 'updated_at') else None
        }

        return success(
            data={"workspace": workspace_data},
            request=request,
            message="Workspace updated successfully"
        )

    except (ResourceNotFoundException, DuplicateResourceException):
        raise
    except Exception as e:
        logger.exception(f"Error updating workspace {workspace_id}")
        db.rollback()
        return error(
            message="Failed to update workspace",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"workspace_id": workspace_id, "error_details": str(e)},
            request=request
        )