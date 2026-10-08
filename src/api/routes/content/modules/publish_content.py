from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import (
    RextExternalServiceException,
    RextValidationException,
)
from src.api.models.content_models.content_version import ContentVersionSource
from src.api.models.content_models.publishing_result import (
    ContentPublishingResult,
    PublishingStatus,
)
from src.api.schema.content_schema import (
    ContentCreate,
    ContentResponse,
    ContentUpdate,
    PublishToSiteRequest,
    RescheduleRequest,
)
from src.api.schema.response.content_responses import (
    DeletedContentResponse,
    RetryContentResponse,
    SaveAndPublishResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.content_service import ContentService
from src.services.user_service import UserService
from src.utils.datetime_utils import moved_to_day
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.wordpress_status import normalize_wordpress_post_status
from src.utils.workspace_utils import resolve_and_verify_workspace

router = APIRouter()

# How close to its time a scheduled publish stops taking moves (see reschedule_publish).
RESCHEDULE_CUTOFF = timedelta(minutes=5)


# -------------------------
# 1. Save Only (New Content)
# -------------------------
@router.post("/save", response_model=SuccessResponse[ContentResponse])
@db_transaction_handler("save content", "Content saved successfully")
@require_permissions("content.create", workspace_scoped=True)
async def save_content(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Save content as a draft WITHOUT publishing it to any WordPress sites.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Save content via service
    service = ContentService(db)

    # Ensure status is 'draft' for this endpoint
    data.status = "draft"

    # A save of an article its generation run already stored is the person's edit of it.
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data,
        version_as=ContentVersionSource.EDIT,
    )

    return success(
        data=content.to_dict(include_relationships=["seo_data"]),
        request=request,
        message="Content saved successfully",
    )


# -------------------------
# 2. Save & Publish (New Content)
# -------------------------
@router.post("/publish", response_model=SuccessResponse[SaveAndPublishResponse])
@db_transaction_handler("publish content", "Content published successfully")
@require_permissions("content.create", "content.publish", workspace_scoped=True)
async def save_and_publish(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    publish_status: str = "publish",
    site_id: Optional[UUID] = None,
    scheduled_at: Optional[datetime] = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Save content AND publish to active WordPress site(s).
    """
    try:
        publish_status = normalize_wordpress_post_status(publish_status)
    except ValueError as exc:
        raise RextValidationException(message=str(exc)) from exc
    logger.info(
        "[PUBLISH STATUS] endpoint=save_and_publish selected_status=%s",
        publish_status,
    )

    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Save content first
    service = ContentService(db)
    # A save of an article its generation run already stored is the person's edit of it.
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data,
        version_as=ContentVersionSource.EDIT,
    )

    # Scheduled posts must follow the account's selected timezone, not the
    # browser's or server's — resolve it once here before publishing.
    user_timezone = "UTC"
    if scheduled_at is not None:
        user_row = await UserService(db).get_user_by_id(UUID(user_id))
        user_timezone = user_row.timezone or "UTC"

    # Publish to active sites via service
    results = await service.publish_to_sites(
        user_id=UUID(user_id),
        content=content,
        workspace_id=workspace.id,
        site_id=site_id,
        publish_status=publish_status,
        scheduled_at=scheduled_at,
        user_timezone=user_timezone,
    )

    successful_results = [r for r in results if r.success]
    all_failed = len(successful_results) == 0

    if all_failed:
        errors = "; ".join(r.error for r in results if r.error)
        raise RextExternalServiceException(
            message=f"Publishing failed for all connected sites. {errors}",
            service_name="Publishing",
        )

    return success(
        data={
            "content": content.to_dict(),
            "publish_results": {
                "content_id": str(content.id),
                "total_sites": len(results),
                "successful": len(successful_results),
                "failed": len(results) - len(successful_results),
                "results": [r.model_dump() for r in results],
                "all_failed": False,
            },
        },
        request=request,
        message="Content published successfully",
    )


# -------------------------
# 3. Publish Existing Content
# -------------------------
@router.post("/{content_id}/publish", response_model=SuccessResponse[SaveAndPublishResponse])
@db_transaction_handler("publish existing content", "Content published successfully")
@require_permissions("content.publish", workspace_scoped=True)
async def publish_existing_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    publish_data: PublishToSiteRequest = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Publish existing content to all active WordPress sites.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Get existing content
    service = ContentService(db)
    content = await service._get_content_or_404(content_id, workspace.id, include_seo=True)

    # Get publish status, site_id, and scheduled_at from request or defaults
    status = "publish"
    site_id = None
    scheduled_at = None
    if publish_data:
        if publish_data.status:
            status = publish_data.status
        if publish_data.site_id:
            site_id = publish_data.site_id
        if publish_data.scheduled_at:
            scheduled_at = publish_data.scheduled_at

    status = normalize_wordpress_post_status(status)
    logger.info(
        "[PUBLISH STATUS] endpoint=publish_existing content_id=%s selected_status=%s",
        content_id,
        status,
    )

    # Scheduled posts must follow the account's selected timezone, not the
    # browser's or server's — resolve it once here before publishing.
    user_timezone = "UTC"
    if scheduled_at is not None:
        user_row = await UserService(db).get_user_by_id(UUID(user_id))
        user_timezone = user_row.timezone or "UTC"

    # Publish to active sites via service
    results = await service.publish_to_sites(
        user_id=UUID(user_id),
        content=content,
        workspace_id=workspace.id,
        site_id=site_id,
        publish_status=status,
        scheduled_at=scheduled_at,
        user_timezone=user_timezone,
    )

    successful_results = [r for r in results if r.success]
    all_failed = len(successful_results) == 0

    if all_failed:
        errors = "; ".join(r.error for r in results if r.error)
        raise RextExternalServiceException(
            message=f"Publishing failed for all connected sites. {errors}",
            service_name="Publishing",
        )

    return success(
        data={
            "content": content.to_dict(),
            "publish_results": {
                "content_id": str(content_id),
                "total_sites": len(results),
                "successful": len(successful_results),
                "failed": len(results) - len(successful_results),
                "results": [r.model_dump() for r in results],
                "all_failed": False,
            },
        },
        request=request,
        message="Content published successfully",
    )


# -------------------------
# Retry Content Generation/Publishing
# -------------------------
@router.post("/{content_id}/retry", response_model=SuccessResponse[RetryContentResponse])
@db_transaction_handler("retry content", "Retry initiated")
@require_permissions("content.publish", workspace_scoped=True)
async def retry_content(
    content_id: UUID,
    workspace_id: str,
    request: Request,
    site_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Retry a failed content operation.

    If site_id is provided, retry specifically for that site.
    If it was a publishing failure, attempts to re-publish.
    If it was a generation failure, transitions back to draft/generating.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service._get_content_or_404(content_id, workspace.id, include_seo=True)

    if content.status != "failed":
        raise HTTPException(
            status_code=400,
            detail=f"Only failed content can be retried. Current status: {content.status}",
        )

    # If we have body content but no WP post ID, it likely failed at publishing
    # (Or if site_id is specified, we assume we want to retry publishing for that site)
    if (content.body_markdown and not content.wordpress_post_id) or site_id:
        logger.info(f"Retrying publishing for content {content_id} (site: {site_id or 'all'})")
        results = await service.publish_to_sites(
            user_id=UUID(user_id), content=content, workspace_id=workspace.id, site_id=site_id
        )
        successful_results = [r for r in results if r.success]
        return success(
            data={
                "content_id": str(content_id),
                "status": content.status,
                "retry_type": "publishing",
                "successful": len(successful_results) > 0,
            },
            request=request,
            message="Retry initiated (publishing)",
        )

    # Otherwise, it might have failed at generation or some other step
    # Reset to draft for now so it can be manually re-triggered or edited
    content.status = "draft"
    content.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return success(
        data={
            "content_id": str(content_id),
            "status": content.status,
            "retry_type": "unspecified_reset_to_draft",
        },
        request=request,
        message="Retry initiated (reset to draft)",
    )


# -------------------------
# Sync CMS Status
# -------------------------
@router.post("/{content_id}/sync", response_model=SuccessResponse[dict])
@db_transaction_handler("sync content status", "Status sync initiated")
@require_permissions("content.read", workspace_scoped=True)
async def sync_content_status(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Manually sync the status of content from all published sites.
    """
    from src.api.models.content_models.publishing_result import ContentPublishingResult
    from src.services.cms_status_service import CMSStatusService

    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Verify content belongs to this workspace before touching CMS APIs
    from src.api.models.content_models import Content

    content_check = await db.execute(
        select(Content).where(
            Content.id == content_id,
            Content.workspace_id == workspace.id,
            Content.deleted_at.is_(None),
        )
    )
    if not content_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Content not found in this workspace.")

    # Fetch all publishing results for this content
    stmt = select(ContentPublishingResult).where(ContentPublishingResult.content_id == content_id)
    results = (await db.execute(stmt)).scalars().all()

    if not results:
        raise HTTPException(status_code=404, detail="No publishing records found for this content.")

    monitor_service = CMSStatusService(db)
    synced_results = []

    for res in results:
        updated = await monitor_service.sync_content_status(res.id)
        if updated:
            synced_results.append(
                {
                    "site_id": str(updated.site_id),
                    "status": updated.status,
                    "external_url": updated.external_url,
                }
            )

    return success(
        data={
            "content_id": str(content_id),
            "synced_sites": len(synced_results),
            "results": synced_results,
        },
        request=request,
        message="CMS status sync completed",
    )


# -------------------------
# Cancel Scheduled Publish
# -------------------------
@router.delete("/{content_id}/schedule", response_model=SuccessResponse[dict])
@db_transaction_handler("cancel scheduled publish", "Schedule cancelled successfully")
@require_permissions("content.update", workspace_scoped=True)
async def cancel_scheduled_publish(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Cancel a pending scheduled publish. Resets content to draft and clears
    all SCHEDULED publishing records for this content.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service._get_content_or_404(content_id, workspace.id)

    if content.status != "scheduled":
        raise HTTPException(
            status_code=400, detail=f"Content is not scheduled. Current status: {content.status}"
        )

    # Clear all SCHEDULED publishing records for this content
    stmt = select(ContentPublishingResult).where(
        ContentPublishingResult.content_id == content_id,
        ContentPublishingResult.status == PublishingStatus.SCHEDULED,
    )
    scheduled_records = (await db.execute(stmt)).scalars().all()

    for rec in scheduled_records:
        rec.status = PublishingStatus.DRAFT
        rec.scheduled_publish_at = None
        rec.sync_error = None

    # Reset content
    content.status = "draft"
    content.wordpress_published_at = None
    content.updated_at = datetime.now(timezone.utc)

    await db.flush()

    return success(
        data={
            "content_id": str(content_id),
            "status": "draft",
            "cancelled_records": len(scheduled_records),
        },
        request=request,
        message="Schedule cancelled successfully",
    )


# -------------------------
# 4. Update Content
# -------------------------
@router.patch("/{content_id}", response_model=SuccessResponse[ContentResponse])
@db_transaction_handler("update content", "Content updated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def update_content(
    content_id: UUID,
    data: ContentUpdate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Update existing content.

    Allows partial updates of content fields, SEO data, and media links.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # The title rule is the service's: a new title only for an article written by hand, and only
    # when the title changes (G55: generated articles may share one).
    service = ContentService(db)
    # A save a person made: the text it leaves is kept as a version (the editor's history).
    content = await service.update_content(
        content_id=content_id,
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data,
        version_as=ContentVersionSource.EDIT,
    )

    return success(
        data=content.to_dict(include_relationships=["seo_data"]),
        request=request,
        message="Content updated successfully",
    )


# -------------------------
# 5. Delete Content
# -------------------------
@router.delete("/{content_id}", response_model=SuccessResponse[DeletedContentResponse])
@db_transaction_handler("delete content", "Content deleted successfully")
@require_permissions("content.delete", workspace_scoped=True)
async def delete_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Soft-delete content.

    Sets deleted_at timestamp instead of permanent removal.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    await service.delete_content(
        content_id=content_id, workspace_id=workspace.id, user_id=UUID(user_id)
    )

    return success(
        data={"deleted_id": str(content_id)},
        request=request,
        message="Content deleted successfully",
    )


# -------------------------
# Move a Scheduled Publish to Another Day
# -------------------------
@router.patch("/{content_id}/schedule", response_model=SuccessResponse[dict])
@db_transaction_handler("reschedule publish", "Schedule moved successfully")
@require_permissions("content.publish", workspace_scoped=True)
async def reschedule_publish(
    content_id: UUID,
    data: RescheduleRequest,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
):
    """
    Move a pending scheduled publish to another day. Every site the content is
    scheduled on moves to the new day at its own time of day, in the account's
    timezone; nothing else about the content or its publishing records changes.
    """
    user_id = user.get("identity")
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    service = ContentService(db)
    content = await service._get_content_or_404(content_id, workspace.id)

    # Locked so a cancel or another move of the same content waits for this one.
    stmt = (
        select(ContentPublishingResult)
        .where(
            ContentPublishingResult.content_id == content_id,
            ContentPublishingResult.status == PublishingStatus.SCHEDULED,
        )
        .with_for_update()
    )
    scheduled_records = (await db.execute(stmt)).scalars().all()

    # The pending records decide, not the content's status: a site published at once beside a
    # scheduled one makes the content "published" while that schedule still waits.
    if not scheduled_records:
        raise HTTPException(
            status_code=400,
            detail=f"Content is not scheduled: no publish is pending. Current status: {content.status}",
        )

    now = datetime.now(timezone.utc)
    # The scheduled publisher (every minute, src/tasks/scheduled_tasks.py) reads due records
    # without a lock, so it could take a record this move is changing: a record that is due,
    # or nearly, is left to it.
    if any(
        rec.scheduled_publish_at is None or rec.scheduled_publish_at <= now + RESCHEDULE_CUTOFF
        for rec in scheduled_records
    ):
        raise HTTPException(
            status_code=409,
            detail="Content publishes within the next few minutes, so its date can't change",
        )

    user_row = await UserService(db).get_user_by_id(UUID(user_id))
    user_timezone = user_row.timezone or "UTC"

    try:
        moved = {
            rec.id: moved_to_day(rec.scheduled_publish_at, data.day, user_timezone)
            for rec in scheduled_records
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(status_code=400, detail="That day is out of range") from exc
    if min(moved.values()) <= now:
        raise HTTPException(status_code=400, detail="The new publish time must be in the future")

    for rec in scheduled_records:
        rec.scheduled_publish_at = moved[rec.id]

    # The calendar shows the content at its first site's time: the records', since a retry
    # moves a record without the content.
    content.wordpress_published_at = min(moved.values())
    content.updated_at = now

    await db.flush()

    return success(
        data={
            "content_id": str(content_id),
            "status": content.status,
            "scheduled_at": content.wordpress_published_at.isoformat(),
            "rescheduled_records": len(scheduled_records),
        },
        request=request,
        message="Schedule moved successfully",
    )
