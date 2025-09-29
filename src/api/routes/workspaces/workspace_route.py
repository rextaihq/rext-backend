from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from src.utils.logger import logger
from src.utils.helper import web_page_scraper
from src.utils.vector_store import add_to_vector_store, delete_vectors
from src.utils.response_utils import success, error, created
from src.api.database.database import get_db
from src.api.security.auth import get_current_user
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.schema.workspace_schema import WorkspaceSchema
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.user_roles import UserRole
from src.api.models.knowledge_models.knowledge_model import BrandVoice, Website, KnowledgeFiles, TextKnowledge
from src.api.schema.knowledge_schema import BrandSchema
from src.model.model import load_model

router = APIRouter(
    prefix="/workspace",
    tags=["workspace"],
    responses={404: {"description": "Not found"}},
)


# -------------------------
# Health Check
# -------------------------
@router.get("/")
def get_status(request: Request):
    logger.info("Workspace Route health check called.")
    return success(
        data={"status": "operational", "service": "workspace_service"},
        request=request,
        message="Workspace service is working!"
    )


# -------------------------
# Get all workspaces for user
# -------------------------
@router.get("/all")
def get_workspaces(
    request: Request, 
    db: Session = Depends(get_db), 
    user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(
            message="User not found",
            context={"user_id": user_id}
        )

    try:
        # Enhanced query to get workspace data with owner info and counts
        from sqlalchemy import func

        workspaces_query = (
            db.query(
                WorkspaceModel,
                Users.display_name.label('owner_name'),
                Users.email.label('owner_email'),
                func.count(Website.id).label('web_knowledge_count'),
                func.count(KnowledgeFiles.id).label('files_count'),
                func.count(TextKnowledge.id).label('text_knowledge_count')
            )
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .join(Users, Users.id == WorkspaceModel.user_id)
            .outerjoin(Website, Website.workspace_id == WorkspaceModel.id)
            .outerjoin(KnowledgeFiles, KnowledgeFiles.workspace_id == WorkspaceModel.id)
            .outerjoin(TextKnowledge, TextKnowledge.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceMembers.user_id == user_id)
            .group_by(WorkspaceModel.id, Users.id)
            .all()
        )

        workspace_data = []
        for result in workspaces_query:
            ws = result[0]  # WorkspaceModel
            owner_name = result[1]
            owner_email = result[2]
            web_count = result[3] or 0
            files_count = result[4] or 0
            text_count = result[5] or 0
            total_knowledge = web_count + files_count + text_count

            workspace_data.append({
                "id": str(ws.id),
                "user_id": str(ws.user_id),
                "name": ws.name,
                "description": ws.description,
                "url": ws.url,
                "created_at": ws.created_at.isoformat() if ws.created_at else None,
                "updated_at": ws.updated_at.isoformat() if ws.updated_at else None,
                "owner": {
                    "name": owner_name,
                    "email": owner_email
                },
                "knowledge_stats": {
                    "web_knowledge": web_count,
                    "files": files_count,
                    "text_knowledge": text_count,
                    "total": total_knowledge
                },
                "status": "active"  # Could be enhanced with actual status logic
            })

        return success(
            data={"workspaces": workspace_data, "total_count": len(workspace_data)},
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

# -------------------------
# Get workspace by ID
# -------------------------
@router.get("/{workspace_id}")
def get_workspace_by_id(workspace_id: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        workspace = (
            db.query(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceModel.id == workspace_id, WorkspaceMembers.user_id == user_id)
            .first()
        )

        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        workspace_data = {
            "id": str(workspace.id),
            "user_id": str(workspace.user_id),
            "name": workspace.name,
            "description": workspace.description,
            "url": workspace.url,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
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


# -------------------------
# Create workspace
# -------------------------
@router.post("/create")
async def create_workspace(
    data: WorkspaceSchema,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    user_id = user.get("identity")

    # Verify user exists
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    # Validate URL
    if not data.url:
        raise WrextValidationException(
            message="Workspace URL is required",
            field_errors={"url": ["URL must be provided and valid"]}
        )

    try:
        # Check for duplicate workspace name for the user
        existing_workspace = db.query(WorkspaceModel).filter_by(name=data.name, user_id=user_id).first()
        if existing_workspace:
            raise DuplicateResourceException(
                message=f"Workspace with title '{data.name}' already exists",
                resource_type="workspace",
                conflicting_field="title",
                conflicting_value=data.name
            )

        # Create workspace
        workspace = WorkspaceModel(
            user_id=user_id,
            name=data.name,
            description=getattr(data, "description", None),
            url=str(data.url)
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

        # Add creator as default member
        member = WorkspaceMembers(
            workspace_id=workspace.id,
            user_id=user_id,
            joined_at=datetime.now(timezone.utc),
            is_default=True,
            status = "active",
            invitation_id = None
        )
        db.add(member)

        # Assign 'admin' role to creator
        admin_role = Role(
            name="admin",
            display_name="Administrator",
            description="Workspace administrator with full permissions",            
        )

        db.add(admin_role)

        # privide the necessary permissions to admin role

        db.commit()
        db.refresh(workspace)
        db.refresh(member)

        # Scrape content
        try:
            chunks, results = await web_page_scraper(urls=[data.url])
            result = results[0]
            if not result.success:
                logger.warning(f"Failed to scrape URL: {data.url}")
            content = result.markdown
        except Exception as scrape_err:
            logger.warning(f"Scraping failed for URL {data.url}: {scrape_err}")
            content = ""

        # Vector store insertion
        try:
            if chunks:
                add_to_vector_store(blog_context=chunks, workspace_id=str(workspace.id))
        except Exception as vec_err:
            logger.warning(f"Vector store insertion failed: {vec_err}")

        # Brand voice extraction (LLM)
        try:
            if content:
                model = load_model()
                structure_model = model.with_structured_output(BrandSchema)
                brand_data = structure_model.invoke(content)

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
        except Exception as llm_err:
            logger.warning(f"Brand voice extraction failed: {llm_err}")

        # Prepare response
        workspace_data = {
            "id": str(workspace.id),
            "name": workspace.name,
            "description": workspace.description,
            "url": workspace.url,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
        }

        return created(
            data={"workspace": workspace_data},
            request=request,
            message="Workspace created successfully"
        )

    except (DuplicateResourceException, WrextValidationException):
        raise
    except Exception as e:
        logger.exception(f"Unexpected error creating workspace {data.name}")
        db.rollback()
        return error(
            message="Failed to create workspace due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )



# -------------------------
# Delete workspace
# -------------------------
@router.delete("/delete/{workspace_id}")
def delete_workspace(workspace_id: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        workspace = (
            db.query(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceModel.id == workspace_id, WorkspaceMembers.user_id == user_id)
            .first()
        )
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        try:
            delete_vectors(vector_id=str(workspace.id))
        except Exception as e:
            logger.warning(f"Failed to delete vectors for workspace {workspace.id}: {e}")

        db.delete(workspace)
        db.commit()

        return success(data={}, request=request, message="Workspace deleted successfully")

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


# -------------------------
# Update workspace
# -------------------------
@router.put("/update/{workspace_id}")
def update_workspace(workspace_id: str, data: WorkspaceSchema, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        workspace = (
            db.query(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceModel.id == workspace_id, WorkspaceMembers.user_id == user_id)
            .first()
        )
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Duplicate title check
        if data.name and data.name != workspace.name:
            existing_workspace = db.query(WorkspaceModel).filter(
                WorkspaceModel.name == data.name,
                WorkspaceModel.user_id == user_id
            ).first()
            if existing_workspace:
                raise DuplicateResourceException(
                    message=f"Workspace with title '{data.name}' already exists",
                    resource_type="workspace",
                    conflicting_field="title",
                    conflicting_value=data.name
                )

        # Update fields
        if data.name:
            workspace.name = data.name
        if data.description is not None:
            workspace.description = data.description
        if data.url:
            workspace.url = str(data.url)
        workspace.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(workspace)

        workspace_data = {
            "id": str(workspace.id),
            "name": workspace.name,
            "description": workspace.description,
            "url": workspace.url,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
            "updated_at": workspace.updated_at.isoformat() if workspace.updated_at else None,
        }

        return success(data={"workspace": workspace_data}, request=request, message="Workspace updated successfully")

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
