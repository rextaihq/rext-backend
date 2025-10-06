from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct
from datetime import datetime, timezone
from uuid import UUID

from src.utils.logger import logger
from src.utils.helper import web_page_scraper
from src.utils.vector_store import add_to_vector_store, delete_vectors
from src.utils.response_utils import success, error, created
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.slug_utils import generate_workspace_slug, generate_unique_slug
from src.utils.workspace_utils import resolve_workspace, resolve_and_verify_workspace
from src.utils.auth_utils import verify_current_user
from src.utils.db_utils import ensure_unique
from src.api.database.async_database import get_async_db
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

router = APIRouter()


# -------------------------
# Health Check
# -------------------------
@router.get("/")
async def get_status(request: Request):
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
@db_transaction_handler("get workspaces", auto_commit=False)
async def get_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Enhanced query to get workspace data with owner info and counts
    workspaces_query = (
        select(
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
        .where(WorkspaceMembers.user_id == user_id)
        .group_by(WorkspaceModel.id, Users.id)
    )

    result = await db.execute(workspaces_query)
    workspaces_results = result.all()

    workspace_data = []
    for result_row in workspaces_results:
        ws = result_row[0]  # WorkspaceModel
        owner_name = result_row[1]
        owner_email = result_row[2]
        web_count = result_row[3] or 0
        files_count = result_row[4] or 0
        text_count = result_row[5] or 0
        members_count = result_row[6] or 0
        total_knowledge = web_count + files_count + text_count

        workspace_data.append({
            "id": str(ws.id),
            "user_id": str(ws.user_id),
            "name": ws.name,
            "slug": ws.slug if hasattr(ws, 'slug') else None,
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
            "status": "active"
        })

    # Return raw data - decorator handles success response
    return {"workspaces": workspace_data, "total_count": len(workspace_data)}

# -------------------------
# Get workspace by ID
# -------------------------
@router.get("/{workspace_id}")
@db_transaction_handler("get workspace by id", auto_commit=False)
async def get_workspace_by_id(workspace_id: str, request: Request, db: AsyncSession = Depends(get_async_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Get brand voice data
    result = await db.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace_id))
    brand_voice = result.scalar_one_or_none()

    # Get comprehensive analytics
    result = await db.execute(select(func.count(Website.id)).where(Website.workspace_id == workspace_id))
    web_count = result.scalar() or 0

    result = await db.execute(select(func.count(KnowledgeFiles.id)).where(KnowledgeFiles.workspace_id == workspace_id))
    files_count = result.scalar() or 0

    result = await db.execute(select(func.count(TextKnowledge.id)).where(TextKnowledge.workspace_id == workspace_id))
    text_count = result.scalar() or 0

    result = await db.execute(select(func.count(WorkspaceMembers.id)).where(WorkspaceMembers.workspace_id == workspace_id))
    members_count = result.scalar() or 0

    # Content analytics - word counts
    web_word_query = select(
        func.sum(Website.word_count).label('total_words'),
        func.avg(Website.word_count).label('avg_words')
    ).where(Website.workspace_id == workspace_id)
    result = await db.execute(web_word_query)
    web_word_stats = result.first()

    file_word_query = select(
        func.sum(KnowledgeFiles.word_count).label('total_words'),
        func.avg(KnowledgeFiles.word_count).label('avg_words')
    ).where(KnowledgeFiles.workspace_id == workspace_id)
    result = await db.execute(file_word_query)
    file_word_stats = result.first()

    total_web_words = int(web_word_stats.total_words or 0)
    avg_web_words = int(web_word_stats.avg_words or 0)
    total_file_words = int(file_word_stats.total_words or 0)
    avg_file_words = int(file_word_stats.avg_words or 0)

    total_words = total_web_words + total_file_words
    estimated_reading_time = total_words // 200

    workspace_data = {
        "id": str(workspace.id),
        "user_id": str(workspace.user_id),
        "name": workspace.name,
        "slug": workspace.slug if hasattr(workspace, 'slug') else None,
        "description": workspace.description,
        "url": workspace.url,
        "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
        "knowledge_stats": {
            "web_knowledge": web_count,
            "files": files_count,
            "text_knowledge": text_count,
            "total": web_count + files_count + text_count
        },
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

    # Return raw data - decorator handles success response
    return {"workspace": workspace_data}


# -------------------------
# Get workspace by slug
# -------------------------
@router.get("/slug/{workspace_slug}")
async def get_workspace_by_slug(
    workspace_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get workspace by slug instead of ID.
    This is the preferred endpoint for frontend routing.
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        # Query workspace by slug
        workspace_query = (
            select(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .where(WorkspaceModel.slug == workspace_slug, WorkspaceMembers.user_id == user_id)
        )
        result = await db.execute(workspace_query)
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_slug)

        workspace_id = workspace.id

        # Get brand voice data
        result = await db.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace_id))
        brand_voice = result.scalar_one_or_none()

        # Get comprehensive analytics with knowledge counts and content metrics
        # Knowledge counts
        result = await db.execute(select(func.count(Website.id)).where(Website.workspace_id == workspace_id))
        web_count = result.scalar() or 0

        result = await db.execute(select(func.count(KnowledgeFiles.id)).where(KnowledgeFiles.workspace_id == workspace_id))
        files_count = result.scalar() or 0

        result = await db.execute(select(func.count(TextKnowledge.id)).where(TextKnowledge.workspace_id == workspace_id))
        text_count = result.scalar() or 0

        result = await db.execute(select(func.count(WorkspaceMembers.id)).where(WorkspaceMembers.workspace_id == workspace_id))
        members_count = result.scalar() or 0

        # Content analytics - word counts
        web_word_query = select(
            func.sum(Website.word_count).label('total_words'),
            func.avg(Website.word_count).label('avg_words')
        ).where(Website.workspace_id == workspace_id)
        result = await db.execute(web_word_query)
        web_word_stats = result.first()

        file_word_query = select(
            func.sum(KnowledgeFiles.word_count).label('total_words'),
            func.avg(KnowledgeFiles.word_count).label('avg_words')
        ).where(KnowledgeFiles.workspace_id == workspace_id)
        result = await db.execute(file_word_query)
        file_word_stats = result.first()

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
@require_permissions("workspace.create", workspace_scoped=False)
async def create_workspace(
    data: WorkspaceSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        # Check for duplicate workspace name for the user
        query = select(WorkspaceModel).where(
            WorkspaceModel.name == data.name,
            WorkspaceModel.user_id == user_id
        )
        result = await db.execute(query)
        if result.scalar_one_or_none():
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
        await db.flush()

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
        await db.flush()

        # Assign 'admin' role to creator
        admin_role = Role(
            name=f"{workspace.name}_admin",
            display_name="Administrator",
            description="Workspace administrator with full permissions",
        )
        db.add(admin_role)
        await db.flush()

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
                    await db.flush()
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
                await db.flush()
            except Exception as direct_err:
                logger.warning(f"Direct brand voice save failed: {direct_err}")

        await db.commit()

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
        await db.rollback()
        return error(
            message="Failed to create workspace due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )




# -------------------------
# Update workspace
# -------------------------
@router.put("/update/{workspace_id}")
@require_permissions("workspace.update", workspace_scoped=True)
async def update_workspace(workspace_id: str, data: WorkspaceSchema, request: Request, db: AsyncSession = Depends(get_async_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

        # Duplicate title check
        if data.name and data.name != workspace.name:
            result = await db.execute(select(WorkspaceModel).where(
                WorkspaceModel.name == data.name,
                WorkspaceModel.user_id == user_id
            ))
            existing_workspace = result.scalar_one_or_none()
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

        await db.commit()
        await db.refresh(workspace)

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
        await db.rollback()
        return error(
            message="Failed to update workspace",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"workspace_id": workspace_id, "error_details": str(e)},
            request=request
        )


# -------------------------
# Delete workspace
# -------------------------
@router.delete("/delete/{workspace_id}")
@require_permissions("workspace.delete", workspace_scoped=True)
async def delete_workspace(workspace_id: str, request: Request, db: AsyncSession = Depends(get_async_db), user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    try:
        workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

        try:
            delete_vectors(vector_id=str(workspace.id))
        except Exception as e:
            logger.warning(f"Failed to delete vectors for workspace {workspace.id}: {e}")

        await db.delete(workspace)
        await db.commit()

        return success(data={}, request=request, message="Workspace deleted successfully")

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting workspace {workspace_id}")
        await db.rollback()
        return error(
            message="Failed to delete workspace",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"workspace_id": workspace_id, "error_details": str(e)},
            request=request
        )
