from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import re

from src.utils.workspace_utils import is_valid_uuid
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextAuthorizationException,
)
from src.api.models.content_models import Content
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers


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
