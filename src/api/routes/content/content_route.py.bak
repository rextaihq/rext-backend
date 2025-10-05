from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, desc, select
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import uuid
import re

from src.utils.logger import logger
from src.utils.response_utils import success, error, created
from src.utils.workspace_utils import get_workspace_id_from_identifier, is_valid_uuid
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException,
    WrextAuthorizationException,
)
from src.api.schema.content_schema import (
    ContentCreate,
    ContentUpdate,
    ContentResponse,
    ContentListResponse,
    ContentMetadataSchema,
    ContentSEODataSchema,
)
from src.api.models.content_models import (
    Content,
    ContentMetadata,
    ContentSEOData,
)
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.users import Users


router = APIRouter(
    prefix="/content",
    tags=["content"],
    responses={404: {"description": "Not found"}},
)


# -------------------------
# Helper Functions
# -------------------------
def slugify(text: str) -> str:
    """Convert text to URL-safe slug"""
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and underscores with hyphens
    text = re.sub(r'[\s_]+', '-', text)
    # Remove non-alphanumeric characters except hyphens
    text = re.sub(r'[^a-z0-9-]', '', text)
    # Remove multiple consecutive hyphens
    text = re.sub(r'-+', '-', text)
    # Strip hyphens from start and end
    text = text.strip('-')
    return text


async def generate_unique_slug(db: AsyncSession, base_slug: str) -> str:
    """Generate unique slug by appending number if needed"""
    slug = base_slug
    counter = 1

    while True:
        result = await db.execute(select(Content).where(Content.slug == slug, Content.deleted_at == None))
        if not result.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


async def verify_workspace_access(db: AsyncSession, workspace_identifier: str, user_id: UUID) -> WorkspaceModel:
    """Verify user has access to workspace (by UUID or slug)"""
    # Resolve workspace ID from either UUID or slug
    if is_valid_uuid(workspace_identifier):
        workspace_id = UUID(workspace_identifier)
        result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.deleted_at == None
            )
        )
        workspace = result.scalar_one_or_none()
    else:
        result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.slug == workspace_identifier,
                WorkspaceModel.deleted_at == None
            )
        )
        workspace = result.scalar_one_or_none()

    if not workspace:
        raise ResourceNotFoundException(
            resource_type="Workspace",
            resource_id=workspace_identifier
        )

    # Check membership
    result = await db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.workspace_id == workspace.id,
            WorkspaceMembers.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        raise WrextAuthorizationException(
            message="User is not a member of this workspace",
            context={"workspace_id": str(workspace_id), "user_id": str(user_id)}
        )

    return workspace


def _build_content_response(content: Content, include_metadata: bool = False, include_seo: bool = False) -> dict:
    """Build content response dictionary with optional related data"""
    response = {
        "id": str(content.id),
        "workspace_id": str(content.workspace_id),
        "topic_id": str(content.topic_id) if content.topic_id else None,
        "created_by_user_id": str(content.created_by_user_id),
        "assigned_to_user_id": str(content.assigned_to_user_id) if content.assigned_to_user_id else None,
        "author_id": str(content.author_id) if content.author_id else None,
        "title": content.title,
        "slug": content.slug,
        "body_markdown": content.body_markdown,
        "body_html": content.body_html,
        "content_format": content.content_format,
        "status": content.status,
        "content_language": content.content_language,
        "created_at": content.created_at.isoformat() if content.created_at else None,
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
        "deleted_at": content.deleted_at.isoformat() if content.deleted_at else None,
    }

    # Include metadata if requested and exists
    if include_metadata and content.content_metadata:
        meta = content.content_metadata
        response["metadata"] = {
            "content_summary": meta.content_summary,
            "content_type": meta.content_type,
            "target_platform": meta.target_platform,
            "target_industry": meta.target_industry,
            "target_audience": meta.target_audience,
            "audience_size": meta.audience_size,
            "complexity_level": meta.complexity_level,
            "content_tone": meta.content_tone,
            "target_region": meta.target_region,
            "content_objectives": meta.content_objectives,
            "source_references": meta.source_references,
            "content_word_count": meta.content_word_count,
            "reading_time_minutes": meta.reading_time_minutes,
            "content_quality_scores": meta.content_quality_scores,
            "featured_image_prompt": meta.featured_image_prompt,
            "featured_image_alt_text": meta.featured_image_alt_text,
        }

    # Include SEO data if requested and exists
    if include_seo and content.seo_data:
        seo = content.seo_data
        response["seo_data"] = {
            "content_primary_keywords": seo.content_primary_keywords,
            "content_secondary_keywords": seo.content_secondary_keywords,
            "content_meta_description": seo.content_meta_description,
            "content_search_intent": seo.content_search_intent,
            "content_seo_score": seo.content_seo_score,
            "content_readability_score": seo.content_readability_score,
        }

    return response


# -------------------------
# List Content for Workspace
# -------------------------
@router.get("/{workspace_id}")
async def list_content(
    workspace_id: str,  # Now accepts both UUID and slug
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status"),
    include_metadata: bool = Query(False, description="Include metadata in response"),
    include_seo: bool = Query(False, description="Include SEO data in response"),
    limit: int = Query(100, le=500, description="Maximum number of items to return"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """List all content for a workspace with optional filtering and pagination"""
    user_id = user.get("identity")

    # Verify access
    workspace = await verify_workspace_access(db, workspace_id, user_id)

    try:
        # Build query
        query = select(Content).where(
            Content.workspace_id == workspace.id,
            Content.deleted_at == None
        )

        # Filter by status if provided
        if status:
            query = query.where(Content.status == status)

        # Get total count
        count_query = select(func.count()).select_from(Content).where(
            Content.workspace_id == workspace.id,
            Content.deleted_at == None
        )
        if status:
            count_query = count_query.where(Content.status == status)

        count_result = await db.execute(count_query)
        total_count = count_result.scalar()

        # Apply pagination and ordering
        query = query.order_by(desc(Content.created_at)).offset(offset).limit(limit)
        result = await db.execute(query)
        content_items = result.scalars().all()

        # Build response
        content_list = [
            _build_content_response(content, include_metadata, include_seo)
            for content in content_items
        ]

        logger.info(f"Listed {len(content_list)} content items for workspace {workspace_id}")

        return success(
            data={
                "content": content_list,
                "total_count": total_count,
                "workspace_id": str(workspace.id),
                "limit": limit,
                "offset": offset
            },
            request=request,
            message=f"Retrieved {len(content_list)} content items"
        )

    except Exception as e:
        logger.error(f"Error listing content for workspace {workspace_id}: {str(e)}")
        return error(
            message="Failed to retrieve content list",
            request=request,
            status_code=500
        )


# -------------------------
# Get Single Content by ID
# -------------------------
@router.get("/{workspace_id}/{content_id}")
async def get_content(
    workspace_id: str,  # Now accepts both UUID and slug
    content_id: UUID,
    request: Request,
    include_metadata: bool = Query(True, description="Include metadata in response"),
    include_seo: bool = Query(True, description="Include SEO data in response"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Get a single content item by ID"""
    user_id = user.get("identity")

    # Verify workspace access
    workspace = await verify_workspace_access(db, workspace_id, user_id)

    try:
        # Get content
        result = await db.execute(
            select(Content).where(
                Content.id == content_id,
                Content.workspace_id == workspace.id,
                Content.deleted_at == None
            )
        )
        content = result.scalar_one_or_none()

        if not content:
            raise ResourceNotFoundException(
                resource_type="Content",
                resource_id=str(content_id)
            )

        content_data = _build_content_response(content, include_metadata, include_seo)

        logger.info(f"Retrieved content {content_id} from workspace {workspace_id}")

        return success(
            data={"content": content_data},
            request=request,
            message="Content retrieved successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving content {content_id}: {str(e)}")
        return error(
            message="Failed to retrieve content",
            request=request,
            status_code=500
        )


# -------------------------
# Create New Content
# -------------------------
@router.post("/{workspace_id}")
async def create_content(
    workspace_id: str,  # Now accepts both UUID and slug
    data: ContentCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Create new content in a workspace"""
    user_id = user.get("identity")

    # Verify workspace access and get the workspace
    workspace = await verify_workspace_access(db, workspace_id, user_id)

    # If workspace_id in body is provided, verify it matches
    if data.workspace_id:
        # Resolve the actual workspace ID
        actual_workspace_id = workspace.id
        if data.workspace_id != actual_workspace_id:
            raise WrextValidationException(
                message="Workspace ID mismatch",
                context={"path_workspace_id": str(workspace_id), "body_workspace_id": str(data.workspace_id)}
            )

    try:
        # Generate unique slug from title
        base_slug = slugify(data.title)
        unique_slug = await generate_unique_slug(db, base_slug)

        # Create content
        content = Content(
            workspace_id=workspace.id,  # Use the actual UUID from workspace object
            topic_id=data.topic_id,
            created_by_user_id=user_id,
            assigned_to_user_id=data.assigned_to_user_id,
            author_id=user_id,  # Default to creator
            title=data.title,
            slug=unique_slug,
            body_markdown=data.body_markdown,
            content_format=data.content_format or "Markdown",
            status=data.status or "draft",
            content_language=data.content_language or "English",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(content)
        await db.flush()

        # Create metadata if provided
        if data.metadata:
            metadata = ContentMetadata(
                content_id=content.id,
                content_summary=data.metadata.content_summary,
                content_type=data.metadata.content_type,
                target_platform=data.metadata.target_platform,
                target_industry=data.metadata.target_industry,
                target_audience=data.metadata.target_audience,
                audience_size=data.metadata.audience_size,
                complexity_level=data.metadata.complexity_level,
                content_tone=data.metadata.content_tone,
                target_region=data.metadata.target_region,
                content_objectives=data.metadata.content_objectives,
                source_references=data.metadata.source_references,
                content_word_count=data.metadata.content_word_count,
                reading_time_minutes=data.metadata.reading_time_minutes,
                content_quality_scores=data.metadata.content_quality_scores,
                featured_image_prompt=data.metadata.featured_image_prompt,
                featured_image_alt_text=data.metadata.featured_image_alt_text,
                created_at=datetime.now(timezone.utc)
            )
            db.add(metadata)

        # Create SEO data if provided
        if data.seo_data:
            seo_data = ContentSEOData(
                content_id=content.id,
                content_primary_keywords=data.seo_data.content_primary_keywords,
                content_secondary_keywords=data.seo_data.content_secondary_keywords,
                content_meta_description=data.seo_data.content_meta_description,
                content_search_intent=data.seo_data.content_search_intent,
                content_seo_score=data.seo_data.content_seo_score,
                content_readability_score=data.seo_data.content_readability_score,
                created_at=datetime.now(timezone.utc)
            )
            db.add(seo_data)

        await db.commit()
        await db.refresh(content)

        content_data = _build_content_response(content, True, True)

        logger.info(f"Created content {content.id} in workspace {workspace_id}")

        return created(
            data={"content": content_data},
            request=request,
            message="Content created successfully"
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating content in workspace {workspace_id}: {str(e)}")
        return error(
            message="Failed to create content",
            request=request,
            status_code=500
        )


# -------------------------
# Update Content
# -------------------------
@router.put("/{workspace_id}/{content_id}")
async def update_content(
    workspace_id: str,  # Now accepts both UUID and slug
    content_id: UUID,
    data: ContentUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Update existing content"""
    user_id = user.get("identity")

    # Verify workspace access
    workspace = await verify_workspace_access(db, workspace_id, user_id)

    try:
        # Get content
        result = await db.execute(
            select(Content).where(
                Content.id == content_id,
                Content.workspace_id == workspace.id,
                Content.deleted_at == None
            )
        )
        content = result.scalar_one_or_none()

        if not content:
            raise ResourceNotFoundException(
                resource_type="Content",
                resource_id=str(content_id)
            )

        # Update fields
        if data.title is not None:
            content.title = data.title
            # Regenerate slug if title changed
            base_slug = slugify(data.title)
            if content.slug != base_slug:
                content.slug = await generate_unique_slug(db, base_slug)

        if data.body_markdown is not None:
            content.body_markdown = data.body_markdown

        if data.body_html is not None:
            content.body_html = data.body_html

        if data.status is not None:
            content.status = data.status

        if data.content_language is not None:
            content.content_language = data.content_language

        if data.assigned_to_user_id is not None:
            content.assigned_to_user_id = data.assigned_to_user_id

        if data.topic_id is not None:
            content.topic_id = data.topic_id

        content.updated_at = datetime.now(timezone.utc)

        # Update metadata if provided
        if data.metadata:
            result = await db.execute(select(ContentMetadata).where(ContentMetadata.content_id == content_id))
            metadata = result.scalar_one_or_none()
            if metadata:
                # Update existing
                if data.metadata.content_summary is not None:
                    metadata.content_summary = data.metadata.content_summary
                if data.metadata.content_type is not None:
                    metadata.content_type = data.metadata.content_type
                if data.metadata.target_platform is not None:
                    metadata.target_platform = data.metadata.target_platform
                if data.metadata.target_industry is not None:
                    metadata.target_industry = data.metadata.target_industry
                if data.metadata.target_audience is not None:
                    metadata.target_audience = data.metadata.target_audience
                if data.metadata.content_word_count is not None:
                    metadata.content_word_count = data.metadata.content_word_count
                if data.metadata.reading_time_minutes is not None:
                    metadata.reading_time_minutes = data.metadata.reading_time_minutes
                metadata.updated_at = datetime.now(timezone.utc)
            else:
                # Create new metadata
                metadata = ContentMetadata(
                    content_id=content.id,
                    content_summary=data.metadata.content_summary,
                    content_type=data.metadata.content_type,
                    target_platform=data.metadata.target_platform,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(metadata)

        # Update SEO data if provided
        if data.seo_data:
            result = await db.execute(select(ContentSEOData).where(ContentSEOData.content_id == content_id))
            seo_data = result.scalar_one_or_none()
            if seo_data:
                # Update existing
                if data.seo_data.content_primary_keywords is not None:
                    seo_data.content_primary_keywords = data.seo_data.content_primary_keywords
                if data.seo_data.content_secondary_keywords is not None:
                    seo_data.content_secondary_keywords = data.seo_data.content_secondary_keywords
                if data.seo_data.content_meta_description is not None:
                    seo_data.content_meta_description = data.seo_data.content_meta_description
                if data.seo_data.content_seo_score is not None:
                    seo_data.content_seo_score = data.seo_data.content_seo_score
                if data.seo_data.content_readability_score is not None:
                    seo_data.content_readability_score = data.seo_data.content_readability_score
                seo_data.updated_at = datetime.now(timezone.utc)
            else:
                # Create new SEO data
                seo_data = ContentSEOData(
                    content_id=content.id,
                    content_primary_keywords=data.seo_data.content_primary_keywords,
                    content_meta_description=data.seo_data.content_meta_description,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(seo_data)

        await db.commit()
        await db.refresh(content)

        content_data = _build_content_response(content, True, True)

        logger.info(f"Updated content {content_id} in workspace {workspace_id}")

        return success(
            data={"content": content_data},
            request=request,
            message="Content updated successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating content {content_id}: {str(e)}")
        return error(
            message="Failed to update content",
            request=request,
            status_code=500
        )


# -------------------------
# Delete Content (Soft Delete)
# -------------------------
@router.delete("/{workspace_id}/{content_id}")
async def delete_content(
    workspace_id: str,  # Now accepts both UUID and slug
    content_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Soft delete content by setting deleted_at timestamp"""
    user_id = user.get("identity")

    # Verify workspace access
    workspace = await verify_workspace_access(db, workspace_id, user_id)

    try:
        # Get content
        result = await db.execute(
            select(Content).where(
                Content.id == content_id,
                Content.workspace_id == workspace.id,
                Content.deleted_at == None
            )
        )
        content = result.scalar_one_or_none()

        if not content:
            raise ResourceNotFoundException(
                resource_type="Content",
                resource_id=str(content_id)
            )

        # Soft delete
        content.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(f"Deleted content {content_id} from workspace {workspace_id}")

        return success(
            data={"content_id": str(content_id)},
            request=request,
            message="Content deleted successfully"
        )

    except ResourceNotFoundException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting content {content_id}: {str(e)}")
        return error(
            message="Failed to delete content",
            request=request,
            status_code=500
        )
