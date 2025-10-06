from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error, created
from src.utils.db_utils import get_or_404
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException,
)
from src.api.schema.content_schema import (
    ContentCreate,
    ContentUpdate,
)
from src.api.models.content_models import (
    Content,
    ContentMetadata,
    ContentSEOData,
)
from .helpers import (
    slugify,
    generate_unique_slug,
)
from src.utils.workspace_utils import resolve_and_verify_workspace


router = APIRouter()


# -------------------------
# Create New Content
# -------------------------
@router.post("/")
@db_transaction_handler("create content", "Content created successfully")
@require_permissions("content.create", workspace_scoped=True)
async def create_content(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Create new content in a workspace.

    Args:
        workspace_id: Workspace UUID or slug (query parameter)
        data: Content creation data

    Requires:
        - JWT authentication
        - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # If workspace_id in body is provided, verify it matches
    if data.workspace_id:
        # Resolve the actual workspace ID
        actual_workspace_id = workspace.id
        if data.workspace_id != actual_workspace_id:
            raise WrextValidationException(
                message="Workspace ID mismatch",
                context={"path_workspace_id": str(workspace_id), "body_workspace_id": str(data.workspace_id)}
            )

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

    await db.flush()
    await db.refresh(content)

    content_data = content.to_dict(include_relationships=["content_metadata", "seo_data"])

    logger.info(f"Created content {content.id} in workspace {workspace_id}")

    # Return raw data - decorator handles success response and commit
    return {"content": content_data}


# -------------------------
# Update Content
# -------------------------
@router.put("/{content_id}")
@db_transaction_handler("update content", "Content updated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def update_content(
    content_id: UUID,
    data: ContentUpdate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Update existing content"""
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

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
            # Check if user is trying to publish content
            if data.status == "published" and content.status != "published":
                from src.utils.rbac_utils import require_permission
                from uuid import UUID as UUIDType
                await require_permission(
                    db=db,
                    user_id=UUIDType(user_id),
                    permission_name="content.publish",
                    workspace_id=workspace.id,
                    resource_name="content"
                )
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

        await db.flush()
        await db.refresh(content)

        content_data = content.to_dict(include_relationships=["content_metadata", "seo_data"])

        logger.info(f"Updated content {content_id} in workspace {workspace_id}")

        # Return raw data - decorator handles success response and commit
        return {"content": content_data}


# -------------------------
# Delete Content (Soft Delete)
# -------------------------
@router.delete("/{content_id}")
@db_transaction_handler("delete content", "Content deleted successfully")
@require_permissions("content.delete", workspace_scoped=True)
async def delete_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Soft delete content by setting deleted_at timestamp"""
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

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

    logger.info(f"Deleted content {content_id} from workspace {workspace_id}")

    # Return raw data - decorator handles success response and commit
    return {"content_id": str(content_id)}
