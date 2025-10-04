from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from uuid import UUID

from src.utils.logger import logger
from src.utils.helper import web_page_scraper
from src.utils.vector_store import add_to_vector_store, delete_vectors
from src.utils.response_utils import success, error, created
from src.utils.slug_utils import generate_workspace_slug, generate_unique_slug
from src.utils.workspace_utils import resolve_workspace
from src.api.database.database import get_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.schema.workspace_schema import WorkspaceSchema, ChangeMemberRoleRequest
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
        from sqlalchemy import func, distinct

        workspaces_query = (
            db.query(
                WorkspaceModel,
                Users.display_name.label('owner_name'),
                Users.email.label('owner_email'),
                func.count(distinct(Website.id)).label('web_knowledge_count'),
                func.count(distinct(KnowledgeFiles.id)).label('files_count'),
                func.count(distinct(TextKnowledge.id)).label('text_knowledge_count'),
                func.count(distinct(WorkspaceMembers.id)).label('members_count')
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
            members_count = result[6] or 0
            total_knowledge = web_count + files_count + text_count

            workspace_data.append({
                "id": str(ws.id),
                "user_id": str(ws.user_id),
                "name": ws.name,
                "slug": ws.slug if hasattr(ws, 'slug') else None,  # Include slug
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
                "members_count": members_count,
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

        # Get brand voice data
        brand_voice = db.query(BrandVoice).filter(BrandVoice.workspace_id == workspace_id).first()

        # Get comprehensive analytics with knowledge counts and content metrics
        from sqlalchemy import func

        # Knowledge counts
        web_count = db.query(func.count(Website.id)).filter(Website.workspace_id == workspace_id).scalar() or 0
        files_count = db.query(func.count(KnowledgeFiles.id)).filter(KnowledgeFiles.workspace_id == workspace_id).scalar() or 0
        text_count = db.query(func.count(TextKnowledge.id)).filter(TextKnowledge.workspace_id == workspace_id).scalar() or 0
        members_count = db.query(func.count(WorkspaceMembers.id)).filter(WorkspaceMembers.workspace_id == workspace_id).scalar() or 0

        # Content analytics - word counts
        web_word_stats = db.query(
            func.sum(Website.word_count).label('total_words'),
            func.avg(Website.word_count).label('avg_words')
        ).filter(Website.workspace_id == workspace_id).first()

        file_word_stats = db.query(
            func.sum(KnowledgeFiles.word_count).label('total_words'),
            func.avg(KnowledgeFiles.word_count).label('avg_words')
        ).filter(KnowledgeFiles.workspace_id == workspace_id).first()

        total_web_words = int(web_word_stats.total_words or 0)
        avg_web_words = int(web_word_stats.avg_words or 0)
        total_file_words = int(file_word_stats.total_words or 0)
        avg_file_words = int(file_word_stats.avg_words or 0)

        # Calculate total content metrics
        total_words = total_web_words + total_file_words
        estimated_reading_time = total_words // 200  # ~200 words per minute

        workspace_data = {
            "id": str(workspace.id),
            "user_id": str(workspace.user_id),
            "name": workspace.name,
            "slug": workspace.slug if hasattr(workspace, 'slug') else None,  # Include slug
            "description": workspace.description,
            "url": workspace.url,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
            # Keep backward compatibility with knowledge_stats at root level
            "knowledge_stats": {
                "web_knowledge": web_count,
                "files": files_count,
                "text_knowledge": text_count,
                "total": web_count + files_count + text_count
            },
            # Also provide detailed analytics
            "analytics": {
                "knowledge_counts": {
                    "web_knowledge": web_count,
                    "files": files_count,
                    "text_knowledge": text_count,
                    "total_knowledge_items": web_count + files_count + text_count
                },
                "content_metrics": {
                    "total_words": total_words,
                    "web_content_words": total_web_words,
                    "file_content_words": total_file_words,
                    "avg_web_article_words": avg_web_words,
                    "avg_file_words": avg_file_words,
                    "estimated_reading_time_minutes": estimated_reading_time
                },
                "team_metrics": {
                    "total_members": members_count
                }
            }
        }

        # Add brand voice data if exists
        if brand_voice:
            workspace_data["brand_voice"] = {
                "about": brand_voice.about,
                "customer_profile": brand_voice.customer_profile,
                "selling_position": brand_voice.selling_position,
                "target_audience": brand_voice.target_audience,
                "brand_voice": brand_voice.brand_voice,
                "competitors": brand_voice.competitors,
                "content_strategy": brand_voice.content_strategy,
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
# Get workspace by slug
# -------------------------
@router.get("/slug/{workspace_slug}")
def get_workspace_by_slug(
    workspace_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Get workspace by slug instead of ID.
    This is the preferred endpoint for frontend routing.
    """
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Query workspace by slug
        workspace = (
            db.query(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceModel.slug == workspace_slug, WorkspaceMembers.user_id == user_id)
            .first()
        )

        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_slug)

        workspace_id = workspace.id

        # Get brand voice data
        brand_voice = db.query(BrandVoice).filter(BrandVoice.workspace_id == workspace_id).first()

        # Get comprehensive analytics with knowledge counts and content metrics
        from sqlalchemy import func

        # Knowledge counts
        web_count = db.query(func.count(Website.id)).filter(Website.workspace_id == workspace_id).scalar() or 0
        files_count = db.query(func.count(KnowledgeFiles.id)).filter(KnowledgeFiles.workspace_id == workspace_id).scalar() or 0
        text_count = db.query(func.count(TextKnowledge.id)).filter(TextKnowledge.workspace_id == workspace_id).scalar() or 0
        members_count = db.query(func.count(WorkspaceMembers.id)).filter(WorkspaceMembers.workspace_id == workspace_id).scalar() or 0

        # Content analytics - word counts
        web_word_stats = db.query(
            func.sum(Website.word_count).label('total_words'),
            func.avg(Website.word_count).label('avg_words')
        ).filter(Website.workspace_id == workspace_id).first()

        file_word_stats = db.query(
            func.sum(KnowledgeFiles.word_count).label('total_words'),
            func.avg(KnowledgeFiles.word_count).label('avg_words')
        ).filter(KnowledgeFiles.workspace_id == workspace_id).first()

        total_web_words = int(web_word_stats.total_words or 0)
        avg_web_words = int(web_word_stats.avg_words or 0)
        total_file_words = int(file_word_stats.total_words or 0)
        avg_file_words = int(file_word_stats.avg_words or 0)

        # Calculate total content metrics
        total_words = total_web_words + total_file_words
        estimated_reading_time = total_words // 200  # ~200 words per minute

        workspace_data = {
            "id": str(workspace.id),
            "user_id": str(workspace.user_id),
            "name": workspace.name,
            "slug": workspace.slug,  # Include slug
            "description": workspace.description,
            "url": workspace.url,
            "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
            # Keep backward compatibility with knowledge_stats at root level
            "knowledge_stats": {
                "web_knowledge": web_count,
                "files": files_count,
                "text_knowledge": text_count,
                "total": web_count + files_count + text_count
            },
            # Comprehensive analytics data
            "analytics": {
                "knowledge_counts": {
                    "web_knowledge": web_count,
                    "files": files_count,
                    "text_knowledge": text_count,
                    "total_knowledge_items": web_count + files_count + text_count
                },
                "content_metrics": {
                    "total_words": total_words,
                    "web_content_words": total_web_words,
                    "file_content_words": total_file_words,
                    "avg_web_article_words": avg_web_words,
                    "avg_file_words": avg_file_words,
                    "estimated_reading_time_minutes": estimated_reading_time
                },
                "team_metrics": {
                    "total_members": members_count
                }
            }
        }

        # Add brand voice data if exists
        if brand_voice:
            workspace_data["brand_voice"] = {
                "id": str(brand_voice.id),
                "workspace_id": str(brand_voice.workspace_id),
                "about": brand_voice.about,
                "customer_profile": brand_voice.customer_profile,
                "selling_position": brand_voice.selling_position,
                "target_audience": brand_voice.target_audience,
                "brand_voice": brand_voice.brand_voice,
                "competitors": brand_voice.competitors,
                "content_strategy": brand_voice.content_strategy,
                "created_at": brand_voice.created_at.isoformat() if brand_voice.created_at else None,
            }

        return success(
            data={"workspace": workspace_data},
            request=request,
            message="Workspace retrieved successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace by slug {workspace_slug}")
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

        # Generate unique slug for workspace
        base_slug = generate_workspace_slug(data.name)
        unique_slug = generate_unique_slug(db, base_slug, WorkspaceModel)

        # Create workspace
        workspace = WorkspaceModel(
            user_id=user_id,
            name=data.name,
            slug=unique_slug,  # Add slug
            description=getattr(data, "description", None),
            url=str(data.url) if data.url else None
        )
        db.add(workspace)
        db.flush() 

        # Add creator as default member
        member = WorkspaceMembers(
            workspace_id=workspace.id,
            user_id=user_id,
            joined_at=datetime.now(timezone.utc),
            is_default=True,
            status="active",
            invitation_id=None
        )
        db.add(member)
        db.flush() 

        # Assign 'admin' role to creator
        admin_role = Role(
            name=f"{workspace.name}_admin",
            display_name="Administrator",
            description="Workspace administrator with full permissions",            
        )
        db.add(admin_role)
        db.flush() 

        # --- Branching logic ---
        brand_voice = None
        if data.url:
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
                    db.flush()
            except Exception as llm_err:
                logger.warning(f"Brand voice extraction failed: {llm_err}")

        else:
            # Directly use provided brand data (from request body)
            try:
                brand_voice = BrandVoice(
                    workspace_id=workspace.id,
                    about=data.about,
                    customer_profile=data.customer_profile,
                    selling_position=data.selling_position,
                    target_audience=data.target_audience,
                    brand_voice=data.brand_voice,
                    competitors=data.competitors,
                    content_strategy=data.content_strategy,
                )
                db.add(brand_voice)
                db.flush()
            except Exception as direct_err:
                logger.warning(f"Direct brand voice save failed: {direct_err}")

        db.commit()

        # Prepare response
        workspace_data = {
            "id": str(workspace.id),
            "name": workspace.name,
            "slug": workspace.slug,  # Include slug
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
# Get workspace members
# -------------------------
@router.get("/{workspace_id}/members")
def get_workspace_members(workspace_id: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Check if user has access to this workspace
        workspace = (
            db.query(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceModel.id == workspace_id, WorkspaceMembers.user_id == user_id)
            .first()
        )
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Get all members of the workspace with user details
        members = (
            db.query(WorkspaceMembers, Users)
            .join(Users, Users.id == WorkspaceMembers.user_id)
            .filter(WorkspaceMembers.workspace_id == workspace_id)
            .all()
        )

        members_data = []
        for member, user_info in members:
            members_data.append({
                "id": str(member.id),
                "user_id": str(member.user_id),
                "workspace_id": str(member.workspace_id),
                "status": member.status,
                "is_default": member.is_default,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "last_activity_at": member.last_activity_at.isoformat() if member.last_activity_at else None,
                "user": {
                    "id": str(user_info.id),
                    "email": user_info.email,
                    "display_name": user_info.display_name,
                    "is_verified": user_info.email_verified,
                }
            })

        return success(
            data={"members": members_data, "total_count": len(members_data)},
            request=request,
            message=f"Retrieved {len(members_data)} members successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace members {workspace_id}")
        return error(
            message="Failed to retrieve workspace members",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Add workspace member
# -------------------------
@router.post("/{workspace_id}/members")
def add_workspace_member(
    workspace_id: str,
    email: str,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Verify user is owner or has access to workspace
        workspace = (
            db.query(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceModel.id == workspace_id, WorkspaceMembers.user_id == user_id)
            .first()
        )
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Find user by email
        new_user = db.query(Users).filter(Users.email == email, Users.deleted_at == None).first()
        if not new_user:
            raise ResourceNotFoundException(resource_type="user", resource_id=email)

        # Check if already a member
        existing_member = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.workspace_id == workspace_id,
            WorkspaceMembers.user_id == new_user.id
        ).first()
        if existing_member:
            raise DuplicateResourceException(
                message=f"User {email} is already a member of this workspace",
                resource_type="workspace_member",
                conflicting_field="user_id",
                conflicting_value=str(new_user.id)
            )

        # Add as member
        new_member = WorkspaceMembers(
            user_id=new_user.id,
            workspace_id=workspace_id,
            status="active",
            is_default=False,
            joined_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        db.add(new_member)
        db.commit()
        db.refresh(new_member)

        return success(
            data={
                "member": {
                    "id": str(new_member.id),
                    "user_id": str(new_user.id),
                    "email": new_user.email,
                    "display_name": new_user.display_name,
                    "status": new_member.status,
                }
            },
            request=request,
            message=f"User {email} added to workspace successfully"
        )

    except (ResourceNotFoundException, DuplicateResourceException):
        raise
    except Exception as e:
        logger.exception(f"Error adding member to workspace {workspace_id}")
        db.rollback()
        return error(
            message="Failed to add member to workspace",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Remove workspace member
# -------------------------
@router.delete("/{workspace_id}/members/{member_id}")
def remove_workspace_member(
    workspace_id: str,
    member_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Verify user has access to workspace
        workspace = (
            db.query(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceModel.id == workspace_id, WorkspaceMembers.user_id == user_id)
            .first()
        )
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Get member to remove
        member = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.id == member_id,
            WorkspaceMembers.workspace_id == workspace_id
        ).first()

        if not member:
            raise ResourceNotFoundException(resource_type="member", resource_id=member_id)

        # Cannot remove workspace owner (is_default=True)
        if member.is_default:
            raise WrextValidationException(
                message="Cannot remove workspace owner",
                validation_errors={"member_id": "This member is the workspace owner"}
            )

        # Delete member
        db.delete(member)
        db.commit()

        return success(
            data={"member_id": member_id},
            request=request,
            message="Member removed from workspace successfully"
        )

    except (ResourceNotFoundException, WrextValidationException):
        raise
    except Exception as e:
        logger.exception(f"Error removing member from workspace {workspace_id}")
        db.rollback()
        return error(
            message="Failed to remove member from workspace",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Change workspace member role
# -------------------------
@router.put("/{workspace_id}/members/{member_id}/role")
def change_member_role(
    workspace_id: str,
    member_id: str,
    role_request: ChangeMemberRoleRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Change the role of a workspace member.

    - Updates the user_roles table for workspace-specific role assignment
    - Cannot change role of workspace owner
    - Validates that the new role exists
    - Logs the role change in audit trail
    """
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Verify user has access to workspace
        workspace = (
            db.query(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceModel.id == workspace_id, WorkspaceMembers.user_id == user_id)
            .first()
        )
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Get member whose role will be changed
        member = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.id == member_id,
            WorkspaceMembers.workspace_id == workspace_id
        ).first()

        if not member:
            raise ResourceNotFoundException(resource_type="member", resource_id=member_id)

        # Cannot change role of workspace owner
        if member.is_default:
            raise WrextValidationException(
                message="Cannot change role of workspace owner",
                validation_errors={"member_id": "This member is the workspace owner"}
            )

        # Verify new role exists
        new_role = db.query(Role).filter(Role.id == role_request.role_id).first()
        if not new_role:
            raise ResourceNotFoundException(resource_type="role", resource_id=role_request.role_id)

        # Cannot assign system roles
        if new_role.is_system_role:
            raise WrextValidationException(
                message="Cannot assign system roles to workspace members",
                validation_errors={"role_id": "This is a system role"}
            )

        # Get or create user_role entry for this workspace
        existing_role = db.query(UserRole).filter(
            UserRole.user_id == member.user_id,
            UserRole.workspace_id == workspace_id
        ).first()

        if existing_role:
            # Update existing role
            old_role_id = existing_role.role_id
            existing_role.role_id = role_request.role_id
            existing_role.assigned_by_user_id = user_id
            existing_role.assigned_at = datetime.now(timezone.utc)
        else:
            # Create new role assignment
            old_role_id = None
            new_user_role = UserRole(
                user_id=member.user_id,
                role_id=role_request.role_id,
                workspace_id=workspace_id,
                assigned_by_user_id=user_id,
                is_primary=False
            )
            db.add(new_user_role)

        db.commit()

        # Get member user details for response
        member_user = db.query(Users).filter(Users.id == member.user_id).first()

        logger.info(
            f"User {user_id} changed role for member {member.user_id} in workspace {workspace_id} "
            f"from {old_role_id} to {role_request.role_id}"
        )

        return success(
            data={
                "member_id": str(member.id),
                "user_id": str(member.user_id),
                "workspace_id": str(workspace_id),
                "role_id": str(role_request.role_id),
                "role_name": new_role.display_name,
                "updated_by": str(user_id),
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            request=request,
            message=f"Role updated to {new_role.display_name} successfully"
        )

    except (ResourceNotFoundException, WrextValidationException):
        raise
    except Exception as e:
        logger.exception(f"Error changing member role in workspace {workspace_id}")
        db.rollback()
        return error(
            message="Failed to change member role",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Get all knowledge for workspace
# -------------------------
@router.get("/{workspace_id}/knowledge/all")
def get_workspace_knowledge(workspace_id: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Resolve workspace from either UUID or slug
        workspace = resolve_workspace(db, workspace_id)
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Check if user has access to this workspace
        member = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.workspace_id == workspace.id,
            WorkspaceMembers.user_id == user_id
        ).first()
        if not member:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Get all knowledge types for this workspace
        web_knowledge = db.query(Website).filter(Website.workspace_id == workspace.id).all()
        file_knowledge = db.query(KnowledgeFiles).filter(KnowledgeFiles.workspace_id == workspace.id).all()
        text_knowledge = db.query(TextKnowledge).filter(TextKnowledge.workspace_id == workspace.id).all()

        # Use to_dict() for consistent structure with type annotation
        web_data = [{"type": "web", **item.to_dict()} for item in web_knowledge]
        file_data = [{"type": "file", **item.to_dict()} for item in file_knowledge]
        text_data = [{"type": "text", **item.to_dict()} for item in text_knowledge]

        return success(
            data={
                "web_knowledge": web_data,
                "file_knowledge": file_data,
                "text_knowledge": text_data,
                "summary": {
                    "web_count": len(web_data),
                    "file_count": len(file_data),
                    "text_count": len(text_data),
                    "total_count": len(web_data) + len(file_data) + len(text_data)
                }
            },
            request=request,
            message="Retrieved all knowledge successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace knowledge {workspace_id}")
        return error(
            message="Failed to retrieve workspace knowledge",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Get web knowledge for workspace
# -------------------------
@router.get("/{workspace_id}/knowledge/web")
def get_workspace_web_knowledge(workspace_id: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Resolve workspace from either UUID or slug
        workspace = resolve_workspace(db, workspace_id)
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Check if user has access to this workspace
        member = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.workspace_id == workspace.id,
            WorkspaceMembers.user_id == user_id
        ).first()
        if not member:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Get web knowledge for this workspace
        web_knowledge = db.query(Website).filter(Website.workspace_id == workspace.id).all()

        # Use to_dict() to match the structure from /api/workspace/web_knowledge/all
        web_data = [item.to_dict() for item in web_knowledge]

        return success(
            data={"web_knowledge": web_data, "total_count": len(web_data)},
            request=request,
            message=f"Retrieved {len(web_data)} web knowledge items"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace web knowledge {workspace_id}")
        return error(
            message="Failed to retrieve web knowledge",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Get file knowledge for workspace
# -------------------------
@router.get("/{workspace_id}/knowledge/files")
def get_workspace_file_knowledge(workspace_id: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Resolve workspace from either UUID or slug
        workspace = resolve_workspace(db, workspace_id)
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Check if user has access to this workspace
        member = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.workspace_id == workspace.id,
            WorkspaceMembers.user_id == user_id
        ).first()
        if not member:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Get file knowledge for this workspace
        file_knowledge = db.query(KnowledgeFiles).filter(KnowledgeFiles.workspace_id == workspace.id).all()

        # Use to_dict() to match the structure from /api/workspace/file/all
        file_data = [item.to_dict() for item in file_knowledge]

        return success(
            data={"file_knowledge": file_data, "total_count": len(file_data)},
            request=request,
            message=f"Retrieved {len(file_data)} file knowledge items"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace file knowledge {workspace_id}")
        return error(
            message="Failed to retrieve file knowledge",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


# -------------------------
# Get text knowledge for workspace
# -------------------------
@router.get("/{workspace_id}/knowledge/text")
def get_workspace_text_knowledge(workspace_id: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Resolve workspace from either UUID or slug
        workspace = resolve_workspace(db, workspace_id)
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Check if user has access to this workspace
        member = db.query(WorkspaceMembers).filter(
            WorkspaceMembers.workspace_id == workspace.id,
            WorkspaceMembers.user_id == user_id
        ).first()
        if not member:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Get text knowledge for this workspace
        text_knowledge = db.query(TextKnowledge).filter(TextKnowledge.workspace_id == workspace.id).all()

        # Use to_dict() to match the structure from /api/workspace/text/all
        text_data = [item.to_dict() for item in text_knowledge]

        return success(
            data={"text_knowledge": text_data, "total_count": len(text_data)},
            request=request,
            message=f"Retrieved {len(text_data)} text knowledge items"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching workspace text knowledge {workspace_id}")
        return error(
            message="Failed to retrieve text knowledge",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
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


# -------------------------
# Update brand voice
# -------------------------
@router.put("/{workspace_id}/brand-voice")
def update_brand_voice(
    workspace_id: str,
    brand_data: BrandSchema,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    user_id = user.get("identity")
    db_user = db.query(Users).filter(Users.id == user_id, Users.deleted_at == None).first()
    if not db_user:
        raise WrextAuthenticationException(message="User not found", context={"user_id": user_id})

    try:
        # Verify workspace access
        workspace = (
            db.query(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .filter(WorkspaceModel.id == workspace_id, WorkspaceMembers.user_id == user_id)
            .first()
        )
        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_id)

        # Get or create brand voice
        brand_voice = db.query(BrandVoice).filter(BrandVoice.workspace_id == workspace_id).first()

        if brand_voice:
            # Update existing brand voice
            brand_voice.about = brand_data.about
            brand_voice.customer_profile = brand_data.customer_profile
            brand_voice.selling_position = brand_data.selling_position
            brand_voice.target_audience = brand_data.target_audience
            brand_voice.brand_voice = brand_data.brand_voice
            brand_voice.competitors = brand_data.competitors
            brand_voice.content_strategy = brand_data.content_pillar
        else:
            # Create new brand voice
            brand_voice = BrandVoice(
                workspace_id=workspace_id,
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

        return success(
            data={
                "brand_voice": {
                    "about": brand_voice.about,
                    "customer_profile": brand_voice.customer_profile,
                    "selling_position": brand_voice.selling_position,
                    "target_audience": brand_voice.target_audience,
                    "brand_voice": brand_voice.brand_voice,
                    "competitors": brand_voice.competitors,
                    "content_strategy": brand_voice.content_strategy,
                }
            },
            request=request,
            message="Brand voice updated successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error updating brand voice for workspace {workspace_id}")
        db.rollback()
        return error(
            message="Failed to update brand voice",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"workspace_id": workspace_id, "error_details": str(e)},
            request=request
        )
