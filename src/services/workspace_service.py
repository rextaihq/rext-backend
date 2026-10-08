"""
Workspace Service - Business Logic for Workspace Operations

This service encapsulates all business logic related to workspace management,
including workspace CRUD operations and analytics.

Responsibilities:
- Workspace CRUD operations
- Workspace analytics and statistics
- Workspace member management (basic)
- Slug generation and uniqueness

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Authentication/authorization (that's decorators)
"""

import re
import unicodedata
from asyncio import create_task, ensure_future, sleep, wait
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from langsmith import trace, traceable
from sqlalchemy import and_, delete, distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.cache.decorators import cached, invalidate_cache, invalidate_cache_key
from src.api.database.async_database import get_async_db_context
from src.api.middleware.exceptions import (
    BusinessRuleViolationException,
    DuplicateResourceException,
    ResourceNotFoundException,
    RextAuthenticationException,
    RextValidationException,
)
from src.api.models.content_models.content import Content
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.sse_service import emit_step_failure, event_stream_manager
from src.services.workspace_pipeline import run_workspace_pipeline
from src.utils.logger import logger
from src.utils.storage import resolve_avatar_url, resolve_media_url

# Track background pipeline tasks to prevent garbage collection
_background_tasks: set = set()
# The operation ids of the pipeline runs this process is running now.
_live_operations: set = set()

# The workspace pipeline runs as a task inside this process, with no queue behind it, so a
# restart or a deploy ends a run without a word. A run recorded as running is gone once it
# started before this process did, or once it has outlived any real run (the pipeline's own
# budget is 90 seconds). A run this process is still running is never gone: it is cut off at
# the same limit instead (_run_pipeline_recorded), so a retry can't start beside it.
_PROCESS_STARTED_AT = datetime.now(timezone.utc)
_PIPELINE_RUN_LIMIT = timedelta(minutes=10)
# How long a run's end waits for the request that created its row to commit it.
_RECORD_ATTEMPTS = 15
_RECORD_RETRY_SECONDS = 2.0


def pipeline_state(workspace: WorkspaceModel) -> Optional[Dict[str, Any]]:
    """The workspace's latest pipeline run, as the dashboard polls it: its status ("running",
    "completed", "failed", or "interrupted" for a running row this process no longer runs), its
    operation id for the SSE stream, and when it started. None when no run is recorded, as for
    a workspace created before runs were: nothing on the row says whether that setup finished
    (a setup can complete and leave no brand voice), so nothing is claimed about it."""
    status = workspace.pipeline_status
    if status is None:
        return None
    started_at = workspace.pipeline_started_at
    if (
        status == "running"
        and workspace.pipeline_operation_id not in _live_operations
        and (
            started_at is None
            or started_at < _PROCESS_STARTED_AT
            or datetime.now(timezone.utc) - started_at > _PIPELINE_RUN_LIMIT
        )
    ):
        status = "interrupted"
    return {
        "status": status,
        "operation_id": workspace.pipeline_operation_id,
        "started_at": started_at.isoformat() if started_at else None,
    }


def _mark_pipeline_started(workspace: WorkspaceModel, operation_id: str) -> None:
    workspace.pipeline_status = "running"
    workspace.pipeline_operation_id = operation_id
    workspace.pipeline_started_at = datetime.now(timezone.utc)


async def _record_pipeline_end(
    db: AsyncSession, workspace_id: UUID, operation_id: str, status: str
) -> bool:
    """Write how a run ended, unless a newer run has taken its place on the row. A creation run
    can end before the request that created its row has committed it, so while the row isn't
    there yet this waits for it (up to about half a minute). Never raises: the run's outcome is
    logged already, and a row left running reads as interrupted.

    True when the row now says how this run ended, or a newer run holds it. False when the
    outcome isn't on record (the row never appeared, or the write failed): the run's terminal
    event is then withheld, so nobody reads "running" on an event that says the run is over."""
    try:
        for _ in range(_RECORD_ATTEMPTS):
            result = await db.execute(
                update(WorkspaceModel)
                .where(
                    WorkspaceModel.id == workspace_id,
                    WorkspaceModel.pipeline_operation_id == operation_id,
                )
                .values(pipeline_status=status)
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            if result.rowcount:
                return True
            current = await db.scalar(
                select(WorkspaceModel.pipeline_operation_id).where(
                    WorkspaceModel.id == workspace_id
                )
            )
            await db.commit()
            if current is not None:
                return True  # a newer run has the row: its own end will be recorded
            await sleep(_RECORD_RETRY_SECONDS)
        logger.warning(
            "The workspace pipeline's row never appeared to record its end",
            extra={"workspace_id": str(workspace_id), "operation_id": operation_id},
        )
        return False
    except Exception as exc:  # noqa: BLE001 - the status is a record, never a new failure
        await db.rollback()
        logger.warning(
            "Could not record the workspace pipeline's end",
            extra={
                "workspace_id": str(workspace_id),
                "operation_id": operation_id,
                "status": status,
                "error": repr(exc),
            },
        )
        return False


async def _run_pipeline_recorded(
    db: AsyncSession,
    *,
    operation_id: str,
    workspace_id: UUID,
    user_id: UUID,
    url: Optional[str],
    description: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    """One pipeline run with its outcome on the workspace's row: written as the run settles, before
    its terminal event goes out (so a read on that event sees it), and "failed" for a run cut off at
    _PIPELINE_RUN_LIMIT. Live in _live_operations meanwhile, so it never reads as interrupted.

    The limit is on the work up to the run's commit (or its failure). Past that point the run is
    left to finish what follows by itself: recording the outcome, then its own terminal event with
    its own payload, so nothing here has to guess whether the record landed or rebuild the event.
    A run cut off before that point is cancelled, which passes the pipeline's `except Exception`
    without a word, so its failure is recorded and its failure event sent from here, the event
    only once the row says "failed"."""
    settled = False

    async def record(status: str) -> bool:
        nonlocal settled
        settled = True
        return await _record_pipeline_end(db, workspace_id, operation_id, status)

    _live_operations.add(operation_id)
    run = ensure_future(
        run_workspace_pipeline(
            db=db,
            operation_id=operation_id,
            workspace_id=workspace_id,
            user_id=user_id,
            url=url,
            description=description,
            name=name,
            on_finished=record,
        )
    )
    try:
        await wait({run}, timeout=_PIPELINE_RUN_LIMIT.total_seconds())
        if run.done() or settled:
            # Finished, or past its commit and finishing: its own outcome, event and exception.
            await run
            return
        run.cancel()
        await wait({run})
        await db.rollback()
        if await _record_pipeline_end(db, workspace_id, operation_id, "failed"):
            await emit_step_failure(
                operation_id=operation_id,
                scope="workspace",
                step="pipeline",
                message="Workspace creation pipeline encountered an error.",
                error=None,
                user_id=user_id,
            )
        raise TimeoutError(f"The workspace pipeline ran past {_PIPELINE_RUN_LIMIT}")
    finally:
        if not run.done():
            # This task was cancelled itself (a shutdown): the run goes with it.
            run.cancel()
        _live_operations.discard(operation_id)


class WorkspaceService:
    """Service for workspace business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize WorkspaceService.

        Args:
            db: Async database session
        """
        self.db = db

    async def list_workspaces_for_user(self, user_id: UUID) -> Dict[str, Any]:
        """Return workspace listing payload for a user."""
        await self._ensure_active_user(user_id)
        workspaces = await self.get_user_workspaces(user_id)
        return {
            "workspaces": workspaces,
            "total_count": len(workspaces),
        }

    async def get_workspace_for_user(self, workspace_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """Fetch workspace details for a member including brand voice data ."""
        await self._ensure_active_user(user_id)
        await self._ensure_membership(workspace_id, user_id)
        return await self.get_workspace_with_brand_voice(workspace_id)

    @traceable(
        name="Create Workspace",
        metadata={"operation": "workspace_create"},
        tags=["WorkspaceService", "Create"],
        project_name="REXT",
    )
    async def create_workspace_for_user(
        self,
        user_id: UUID,
        name: str,
        timezone: Optional[str],
        url: Optional[str],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a workspace and trigger the background onboarding pipeline.

        With no website, `description` is what the owner says of the business: it is kept as
        the brand voice's `about`, and the pipeline drafts the rest of the voice from it.

        Returns immediately with workspace metadata and an SSE operation ID.
        """
        await self._ensure_active_user(user_id)
        with trace(name="Create Workspace Record"):
            workspace = await self.create_workspace(
                user_id=user_id, name=name, tz=timezone, url=url
            )
            await self.db.refresh(workspace)
            if not url and description:
                # Kept with the workspace itself, in the owner's words: a run that a restart
                # ends before it saves anything can then be run again from it.
                self.db.add(BrandVoice(workspace_id=workspace.id, about=description))

        with trace(name="Assign Roles & Permissions"):
            await self.create_workspace_member(
                workspace.id, user_id, is_default=True, status="active"
            )
            owner_role = await self._get_workspace_owner_role()
            await self._assign_role_to_user(owner_role.id, user_id, workspace.id)

        operation_id = str(uuid4())
        _mark_pipeline_started(workspace, operation_id)
        await self.db.flush()

        # Register ownership so only this user can publish events to this operation
        await event_stream_manager.set_operation_owner(operation_id, user_id)

        async def run_pipeline() -> None:
            with trace(
                name="Run Workspace Pipeline",
                inputs={"operation_id": operation_id, "url": url},
            ):
                async with get_async_db_context() as bg_db:
                    try:
                        await _run_pipeline_recorded(
                            bg_db,
                            operation_id=operation_id,
                            workspace_id=workspace.id,
                            user_id=user_id,
                            url=url,
                            description=description,
                            name=name,
                        )
                    except Exception as exc:
                        logger.error(
                            "Workspace pipeline failed",
                            extra={
                                "operation_id": operation_id,
                                "workspace_id": str(workspace.id),
                                "error": str(exc),
                            },
                            exc_info=True,
                        )
                        raise

        task = create_task(run_pipeline())
        _background_tasks.add(task)

        def handle_completion(pipeline_task) -> None:

            _background_tasks.discard(pipeline_task)
            with trace(name="Workspace Completion"):
                try:
                    pipeline_task.result()
                    logger.info(
                        "Workspace pipeline completed successfully",
                        extra={
                            "operation_id": operation_id,
                            "workspace_id": str(workspace.id),
                        },
                    )
                except Exception as exc:
                    logger.error(
                        "Workspace pipeline task raised exception",
                        extra={
                            "operation_id": operation_id,
                            "workspace_id": str(workspace.id),
                            "error": str(exc),
                        },
                        exc_info=True,
                    )

        task.add_done_callback(handle_completion)

        logger.info(
            "Workspace created and background pipeline scheduled",
            extra={"workspace_id": str(workspace.id), "operation_id": operation_id},
        )

        return {
            "workspace": self._serialize_workspace(workspace),
            "operation_id": operation_id,
        }

    async def refresh_brand_voice_for_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        draft_again: bool = False,
    ) -> str:
        """
        Re-run the workspace onboarding pipeline to refresh brand voice data.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID requesting refresh

        Returns:
            Operation identifier for SSE tracking
        """
        await self._ensure_active_user(user_id)
        workspace = await self._ensure_membership(workspace_id, user_id)

        # The row stays locked until this request commits, so a second request at the same
        # moment waits here and then sees this run.
        await self.db.refresh(workspace, with_for_update=True)
        state = pipeline_state(workspace)
        if state and state["status"] == "running":
            # Two runs at once would race each other's writes to the brand voice.
            raise BusinessRuleViolationException(
                message="The workspace's website is still being read. Wait for it to finish.",
                rule_name="workspace_pipeline_running",
            )
        description = None
        if not workspace.url:
            # No website to read. Only the retry of a run that failed or was interrupted drafts
            # the voice again, from the owner's description (rext-control#853).
            description = await self._description_to_draft_from(workspace) if draft_again else None
            if not description:
                raise RextValidationException(
                    message="Workspace URL is required to refresh brand voice",
                    field_errors={"url": ["Workspace must have a valid URL before refreshing"]},
                )

        operation_id = str(uuid4())
        _mark_pipeline_started(workspace, operation_id)
        await self.db.flush()
        workspace_id, url, name = workspace.id, workspace.url, workspace.name

        # Register ownership so only this user can publish events to this operation
        await event_stream_manager.set_operation_owner(operation_id, user_id)

        async def run_pipeline() -> None:
            async with get_async_db_context() as bg_db:
                try:
                    await _run_pipeline_recorded(
                        bg_db,
                        operation_id=operation_id,
                        workspace_id=workspace_id,
                        user_id=user_id,
                        url=url,
                        description=description,
                        name=name,
                    )
                except Exception as exc:
                    logger.error(
                        "Workspace refresh pipeline failed",
                        extra={
                            "operation_id": operation_id,
                            "workspace_id": str(workspace_id),
                            "error": str(exc),
                        },
                        exc_info=True,
                    )
                    raise

        task = create_task(run_pipeline())
        _background_tasks.add(task)

        def handle_completion(pipeline_task) -> None:
            _background_tasks.discard(pipeline_task)
            try:
                pipeline_task.result()
            except Exception as exc:
                logger.error(
                    "Workspace refresh pipeline raised exception",
                    extra={
                        "operation_id": operation_id,
                        "workspace_id": str(workspace.id),
                        "error": str(exc),
                    },
                    exc_info=True,
                )

        task.add_done_callback(handle_completion)

        logger.info(
            "Brand voice refresh scheduled",
            extra={"workspace_id": str(workspace.id), "operation_id": operation_id},
        )

        return operation_id

    async def _description_to_draft_from(self, workspace: WorkspaceModel) -> Optional[str]:
        """What a workspace with no website is drafted from a second time: the owner's
        description of the business, kept as its brand voice's About since it was created."""
        about = await self.db.scalar(
            select(BrandVoice.about).where(BrandVoice.workspace_id == workspace.id)
        )
        return (about or "").strip() or None

    async def retry_pipeline_for_user(self, workspace_id: UUID, user_id: UUID) -> str:
        """Run the workspace pipeline again after its last run failed or was interrupted (a
        restart or a deploy ends a run). Returns the new run's operation id."""
        await self._ensure_active_user(user_id)
        workspace = await self._ensure_membership(workspace_id, user_id)
        state = pipeline_state(workspace)
        if not state or state["status"] not in ("failed", "interrupted"):
            raise BusinessRuleViolationException(
                message="Only a run that failed or was interrupted can be retried.",
                rule_name="workspace_pipeline_not_retryable",
            )
        # A voice that was drafted has been the owner's to edit since, so only this path (a run
        # that left nothing, or not all of it) drafts a workspace with no website again.
        return await self.refresh_brand_voice_for_user(workspace_id, user_id, draft_again=True)

    async def delete_workspace_for_user(self, workspace_id: UUID, user_id: UUID) -> None:
        """Delete workspace after verifying membership and cleanup."""
        await self._ensure_active_user(user_id)
        await self._ensure_membership(workspace_id, user_id)
        await self.delete_workspace(workspace_id, user_id)

    async def update_workspace_for_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
        name: Optional[str],
        timezone: Optional[str],
        url: Optional[str],
    ) -> Dict[str, Any]:
        """Update workspace metadata for a member."""
        await self._ensure_active_user(user_id)
        workspace = await self._ensure_membership(workspace_id, user_id)

        if name and name != workspace.name:
            await self._ensure_unique_workspace_name(name, user_id)

        updated = await self.update_workspace(
            workspace_id=workspace_id,
            name=name,
            tz=timezone,
            url=url,
        )
        await self.db.flush()
        await self.db.refresh(updated)
        return self._serialize_workspace(updated)

    async def get_user_workspaces(
        self, user_id: UUID, sort_by: str = "created_at"
    ) -> List[Dict[str, Any]]:
        """
        Get all workspaces for a user with counts.

        Optimized query that fetches workspace data with member counts in a single query.

        Args:
            user_id: User UUID

        Returns:
            List of workspace dictionaries with counts
        """
        # Enhanced query to get workspace data with owner info and counts
        workspaces_query = (
            select(
                WorkspaceModel,
                Users.display_name.label("owner_name"),
                Users.email.label("owner_email"),
                Users.avatar_url.label("owner_avatar_url"),
                func.count(distinct(WorkspaceMembers.id)).label("members_count"),
            )
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .join(Users, Users.id == WorkspaceModel.user_id)
            .where(
                WorkspaceMembers.user_id == user_id,
                WorkspaceModel.deleted_at.is_(None),  # Filter out soft-deleted workspaces
            )
            .group_by(WorkspaceModel.id, Users.id)
        )
        if sort_by == "name":
            workspaces_query = workspaces_query.order_by(
                func.lower(WorkspaceModel.name).asc(), WorkspaceModel.id.asc()
            )
        else:
            workspaces_query = workspaces_query.order_by(
                WorkspaceModel.created_at.desc(), WorkspaceModel.id.desc()
            )

        result = await self.db.execute(workspaces_query)
        workspaces_results = result.all()

        workspace_data = []
        for result_row in workspaces_results:
            ws = result_row[0]  # WorkspaceModel
            owner_name = result_row[1]
            owner_email = result_row[2]
            owner_avatar_url = result_row[3]
            members_count = result_row[4] or 0

            workspace_data.append(
                {
                    "id": str(ws.id),
                    "user_id": str(ws.user_id),
                    "name": ws.name,
                    "slug": ws.slug,
                    "timezone": ws.timezone,
                    "url": ws.url,
                    "favicon_url": resolve_media_url(ws.favicon_url),
                    "created_at": ws.created_at.isoformat() if ws.created_at else None,
                    "updated_at": ws.updated_at.isoformat() if ws.updated_at else None,
                    "owner": {
                        "id": str(ws.user_id),
                        "full_name": owner_name,
                        "name": owner_name,
                        "email": owner_email,
                        "avatar_url": resolve_avatar_url(owner_avatar_url),
                    },
                    "members_count": members_count,
                }
            )

        logger.info(
            "Retrieved workspaces for user",
            extra={"user_id": str(user_id), "count": len(workspace_data)},
        )

        return workspace_data

    async def get_workspace_analytics(self, workspace_id: UUID) -> Dict[str, Any]:
        """
        Get the member and content counts of a workspace in one query.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Dict with analytics data
        """
        members_count_subq = (
            select(func.count(WorkspaceMembers.id))
            .where(WorkspaceMembers.workspace_id == workspace_id)
            .correlate(None)
            .scalar_subquery()
        )
        content_count_subq = (
            select(func.count(Content.id))
            .where(
                Content.workspace_id == workspace_id,
                Content.deleted_at.is_(None),
            )
            .correlate(None)
            .scalar_subquery()
        )
        result = await self.db.execute(
            select(
                members_count_subq.label("members_count"),
                content_count_subq.label("content_count"),
            )
        )
        row = result.one()

        analytics = {
            "members_count": row.members_count or 0,
            "content_count": row.content_count or 0,
        }

        logger.info(
            "Retrieved analytics for workspace",
            extra={"workspace_id": str(workspace_id)},
        )

        return analytics

    @cached(
        key_prefix="workspace:brand_voice",
        ttl=600,
        key_builder=lambda self, workspace_id: str(workspace_id),
    )
    async def get_workspace_with_brand_voice(self, workspace_id: UUID) -> Dict[str, Any]:
        """
        Get workspace with brand voice data.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Dict with workspace and brand voice data

        Raises:
            ResourceNotFoundException: If workspace not found
        """
        workspace = await self.get_workspace(workspace_id)

        # Get brand voice data
        result = await self.db.execute(
            select(BrandVoice).where(BrandVoice.workspace_id == workspace_id)
        )
        brand_voice = result.scalar_one_or_none()

        workspace_data = {
            "id": str(workspace.id),
            "user_id": str(workspace.user_id),
            "name": workspace.name,
            "slug": workspace.slug,
            "timezone": workspace.timezone,
            "url": workspace.url,
            "favicon_url": resolve_media_url(workspace.favicon_url),
            "owner": {
                "id": str(workspace.owner.id),
                "full_name": workspace.owner.full_name,
                "name": workspace.owner.full_name,
                "email": workspace.owner.email,
                "avatar_url": resolve_avatar_url(workspace.owner.avatar_url),
            }
            if workspace.owner
            else None,
            "created_at": (workspace.created_at.isoformat() if workspace.created_at else None),
            "updated_at": (workspace.updated_at.isoformat() if workspace.updated_at else None),
        }

        # Add brand voice if exists
        if brand_voice:
            workspace_data["brand_voice"] = {
                "id": str(brand_voice.id),
                "workspace_id": str(brand_voice.workspace_id),
                "brand_name": brand_voice.brand_name,
                "about": brand_voice.about,
                "customer_profile": brand_voice.customer_profile,
                "selling_position": brand_voice.selling_position,
                "target_audience": brand_voice.target_audience,
                "brand_voice": brand_voice.brand_voice,
                "competitors": brand_voice.competitors,
                "content_pillar": brand_voice.content_pillar or [],
                "content_strategy": brand_voice.content_pillar
                or [],  # Backward compatibility alias
                "created_at": (
                    brand_voice.created_at.isoformat() if brand_voice.created_at else None
                ),
            }

        return workspace_data

    async def get_workspace(self, workspace_id: UUID) -> WorkspaceModel:
        """
        Get workspace by ID.

        Args:
            workspace_id: Workspace UUID

        Returns:
            WorkspaceModel object

        Raises:
            ResourceNotFoundException: If workspace not found
        """
        result = await self.db.execute(
            select(WorkspaceModel)
            .options(selectinload(WorkspaceModel.owner))
            .where(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.deleted_at.is_(None),  # Exclude soft-deleted workspaces
            )
        )
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise ResourceNotFoundException(
                resource_type="Workspace", resource_id=str(workspace_id)
            )

        return workspace

    async def get_workspace_by_slug_for_user(self, slug: str, user_id: UUID) -> WorkspaceModel:
        """
        Get workspace by slug for a specific user (verifies membership).

        Args:
            slug: Workspace slug
            user_id: User UUID

        Returns:
            WorkspaceModel object

        Raises:
            ResourceNotFoundException: If workspace not found or user not a member
        """
        result = await self.db.execute(
            select(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .where(
                WorkspaceModel.slug == slug,
                WorkspaceMembers.user_id == user_id,
                WorkspaceModel.deleted_at.is_(None),
            )
        )
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=slug)

        return workspace

    async def get_workspace_by_id_or_slug_for_user(
        self, identifier: str, user_id: UUID
    ) -> WorkspaceModel:
        """
        Get workspace by ID or slug for a specific user (verifies membership).
        Automatically detects whether identifier is UUID or slug.

        Args:
            identifier: Workspace UUID or slug
            user_id: User UUID

        Returns:
            WorkspaceModel object

        Raises:
            ResourceNotFoundException: If workspace not found or user not a member
        """
        # Check if identifier is a UUID or slug
        is_uuid = False
        try:
            UUID(identifier)
            is_uuid = True
        except ValueError:
            is_uuid = False

        # Build query based on whether it's UUID or slug
        if is_uuid:
            query = (
                select(WorkspaceModel)
                .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
                .where(
                    WorkspaceModel.id == UUID(identifier),
                    WorkspaceMembers.user_id == user_id,
                    WorkspaceModel.deleted_at.is_(None),
                )
            )
        else:
            query = (
                select(WorkspaceModel)
                .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
                .where(
                    WorkspaceModel.slug == identifier,
                    WorkspaceMembers.user_id == user_id,
                    WorkspaceModel.deleted_at.is_(None),
                )
            )

        result = await self.db.execute(query)
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise ResourceNotFoundException(resource_type="workspace", resource_id=identifier)

        return workspace

    async def verify_user_is_workspace_owner(self, workspace_id: UUID, user_id: UUID) -> bool:
        """
        Verify if user has workspace owner role.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID

        Returns:
            True if user is workspace owner, False otherwise

        Raises:
            ForbiddenException: If user is not workspace owner
        """
        # Query UserRole and Role to check for workspace_owner
        query = (
            select(UserRole)
            .join(Role, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                UserRole.workspace_id == workspace_id,
                Role.hierarchy_level >= 60,  # workspace_owner or higher (60 is workspace_owner)
            )
        )

        result = await self.db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            from src.api.middleware.exceptions import RextAuthorizationException

            raise RextAuthorizationException(
                message="Only workspace owners can perform this action"
            )

        return True

    async def create_workspace(
        self,
        user_id: UUID,
        name: str,
        tz: Optional[str] = None,
        url: Optional[str] = None,
        slug: Optional[str] = None,
    ) -> WorkspaceModel:
        """
        Create new workspace with owner membership.

        Business Rules:
        - Workspace name must be unique per user
        - Slug is auto-generated from name (or provided)
        - Creator is automatically added as owner

        Args:
            user_id: User UUID (owner)
            name: Workspace name
            tz: IANA timezone identifier (e.g., 'America/New_York', 'UTC')
            url: Workspace URL
            slug: Optional pre-generated slug

        Returns:
            Created WorkspaceModel object

        Raises:
            DuplicateResourceException: If workspace name already exists for user
        """
        # TEMPORARY: Disable duplicate name check for testing
        # result = await self.db.execute(
        #     select(WorkspaceModel).where(
        #         WorkspaceModel.name == name, WorkspaceModel.user_id == user_id
        #     )
        # )
        # if result.scalar_one_or_none():
        #     raise DuplicateResourceException(
        #         message=f"Workspace with name '{name}' already exists",
        #         resource_type="workspace",
        #         conflicting_field="name",
        #         conflicting_value=name,
        #     )

        # Ensure unique slug
        base_slug = self._slugify(slug or name)
        slug = await self._generate_unique_slug(base_slug, user_id)

        # Create workspace
        workspace = WorkspaceModel(
            user_id=user_id,
            name=name,
            slug=slug,
            timezone=tz,
            url=url,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(workspace)
        await self.db.flush()

        logger.info(
            "Workspace created",
            extra={"workspace_id": str(workspace.id), "user_id": str(user_id), "name": name},
        )

        return workspace

    async def create_workspace_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
        is_default: bool = True,
        status: str = "active",
    ) -> WorkspaceMembers:
        """
        Add a member to workspace.

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID
            is_default: Whether this is default workspace for user
            status: Member status

        Returns:
            Created WorkspaceMembers object
        """
        member = WorkspaceMembers(
            workspace_id=workspace_id,
            user_id=user_id,
            joined_at=datetime.now(timezone.utc),
            is_default=is_default,
            status=status,
            invitation_id=None,
        )
        self.db.add(member)
        await self.db.flush()

        logger.info(
            "Added member to workspace",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id)},
        )

        return member

    async def update_workspace(
        self,
        workspace_id: UUID,
        name: Optional[str] = None,
        tz: Optional[str] = None,
        url: Optional[str] = None,
    ) -> WorkspaceModel:
        """
        Update workspace details.

        Args:
            workspace_id: Workspace UUID
            name: New workspace name (optional)
            tz: New timezone (optional)
            url: New URL (optional)

        Returns:
            Updated WorkspaceModel object

        Raises:
            ResourceNotFoundException: If workspace not found
        """
        workspace = await self.get_workspace(workspace_id)

        if name is not None:
            # Slug tracks the name. The old slug stops resolving immediately, so
            # callers must redirect to the returned slug after a rename - see
            # GeneralInfoSection on the frontend.
            renamed = name != workspace.name
            workspace.name = name

            if renamed:
                base_slug = self._slugify(name)
                workspace.slug = await self._generate_unique_slug(
                    base_slug, workspace.user_id, exclude_id=workspace_id
                )

        if tz is not None:
            workspace.timezone = tz

        if url is not None:
            workspace.url = url

        workspace.updated_at = datetime.now(timezone.utc)

        # GET /workspaces/{slug} serves from this Redis key (ttl 600s); without
        # this the settings page keeps showing the old name/url for 10 minutes.
        await invalidate_cache_key(f"workspace:brand_voice:{workspace_id}")

        logger.info(
            "Workspace updated",
            extra={"workspace_id": str(workspace_id)},
        )

        return workspace

    async def transfer_ownership(
        self, workspace_id: UUID, current_owner_id: UUID, new_owner_id: UUID
    ) -> WorkspaceModel:
        """
        Hand the workspace to another active member.

        The new owner's workspace roles are replaced by workspace_owner; the
        previous owner drops to workspace_admin so they keep managing access
        without holding ownership. Only the current owner may call this.
        """
        workspace = await self.get_workspace(workspace_id)
        if workspace.user_id != current_owner_id:
            from src.api.middleware.exceptions import RextAuthorizationException

            raise RextAuthorizationException(
                message="Only the workspace owner can transfer ownership"
            )
        if new_owner_id == current_owner_id:
            raise RextValidationException(
                message="You already own this workspace",
                field_errors={"new_owner_user_id": ["Pick a different member"]},
            )

        member = (
            await self.db.execute(
                select(WorkspaceMembers)
                .join(Users, Users.id == WorkspaceMembers.user_id)
                .where(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == new_owner_id,
                    WorkspaceMembers.status == "active",
                    Users.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not member:
            raise RextValidationException(
                message="The new owner must be an active member of this workspace",
                field_errors={"new_owner_user_id": ["User not an active member"]},
            )

        owner_role = await self._get_workspace_owner_role()
        admin_role = (
            await self.db.execute(
                select(Role).where(Role.name == "workspace_admin", Role.is_workspace_role)
            )
        ).scalar_one_or_none()
        if not admin_role:
            raise ValueError("Workspace role 'workspace_admin' not found")

        # The enforce_single_workspace_owner trigger rejects a second owner row,
        # so clear both users' workspace roles before inserting the new ones.
        await self.db.execute(
            delete(UserRole).where(
                UserRole.workspace_id == workspace_id,
                UserRole.user_id.in_([current_owner_id, new_owner_id]),
            )
        )
        await self.db.flush()
        await self._assign_role_to_user(owner_role.id, new_owner_id, workspace_id)
        await self._assign_role_to_user(admin_role.id, current_owner_id, workspace_id)

        workspace.user_id = new_owner_id
        workspace.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        for uid in (current_owner_id, new_owner_id):
            await invalidate_cache(f"user:permissions:{uid}:*")
        await invalidate_cache_key(f"workspace:brand_voice:{workspace_id}")

        logger.info(
            "Workspace ownership transferred",
            extra={
                "workspace_id": str(workspace_id),
                "from_user_id": str(current_owner_id),
                "to_user_id": str(new_owner_id),
            },
        )
        return workspace

    async def delete_workspace(self, workspace_id: UUID, user_id: UUID) -> None:
        """
        Soft delete workspace (30-day recovery period).

        Business Rules:
        - Soft delete: Sets deleted_at timestamp
        - 30-day recovery period before permanent deletion
        - Only workspace owner can delete
        - Related data remains intact for recovery

        Args:
            workspace_id: Workspace UUID
            user_id: User performing the deletion

        Raises:
            ResourceNotFoundException: If workspace not found
        """

        # Verify ownership first
        await self.verify_user_is_workspace_owner(workspace_id, user_id)

        workspace = await self.get_workspace(workspace_id)

        # Soft delete: set deleted_at and deleted_by
        workspace.deleted_at = datetime.now(timezone.utc)
        workspace.deleted_by = user_id

        logger.info(
            "Workspace soft deleted",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id)},
        )

    async def permanently_delete_workspace(self, workspace_id: UUID, user_id: UUID) -> str:
        """
        Permanently delete a workspace that is already in trash.

        Irreversible: the row and everything hanging off it are gone. All the
        child tables carry ON DELETE CASCADE on their workspace_id (content,
        personas, brand voices, media, notifications, integrations, members,
        invitations), so the single row delete takes them with it, and
        audit_logs / email_log are deliberately ON DELETE SET NULL so the trail
        outlives the workspace. The favicon object is outside the database and
        is cleared separately, best-effort, by _purge_workspace_storage().

        Business Rules:
        - Only the workspace owner can do it
        - The workspace must ALREADY be soft-deleted. A live workspace has to go
          through delete_workspace() first, so this can never be the call that
          destroys something the user is still working in.
        - No 30-day window check: the whole point is to empty the trash early,
          and an expired workspace must still be removable.

        Args:
            workspace_id: Workspace UUID
            user_id: User performing the deletion

        Returns:
            The deleted workspace's name (the object is unusable afterwards)

        Raises:
            ResourceNotFoundException: If workspace not found or not soft-deleted
        """
        # Ownership first — role checks are independent of deleted_at, same as
        # delete_workspace()/restore_workspace().
        await self.verify_user_is_workspace_owner(workspace_id, user_id)

        workspace = await self.get_deleted_workspace(workspace_id)
        workspace_name = workspace.name

        # user_roles is the ONE workspace child table whose FK has no ondelete
        # rule (user_roles.workspace_id is a plain nullable FK). Left to
        # SQLAlchemy's default for a one-to-many with no cascade, deleting the
        # parent UPDATEs these rows to workspace_id = NULL — and a UserRole with
        # a NULL workspace is an unscoped, platform-wide grant. Every member who
        # held workspace_owner on this workspace would silently walk away with a
        # global workspace_owner role. Delete them explicitly instead.
        #
        # ponytail: explicit delete rather than a migration adding ON DELETE
        # CASCADE to user_roles.workspace_id — this is the only hard-delete path
        # for a workspace today. Add the constraint if a second one appears.
        await self.db.execute(delete(UserRole).where(UserRole.workspace_id == workspace_id))

        # Rows cascade, bytes don't. The favicon is a media object
        # (workspace_favicon.store_favicon), so read its key off the row while it
        # still exists, then clear it once the delete has gone through.
        favicon_object = workspace.favicon_url

        await self.db.delete(workspace)
        await self.db.flush()

        await self._purge_workspace_storage(workspace_id, favicon_object)

        logger.info(
            "Workspace permanently deleted",
            extra={
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "workspace_name": workspace_name,
            },
        )

        return workspace_name

    async def _purge_workspace_storage(
        self,
        workspace_id: UUID,
        favicon_object: Optional[str] = None,
    ) -> None:
        """
        Delete a permanently-deleted workspace's stored objects.

        Best-effort by design: a storage failure must not raise, because that
        would roll back a delete the caller already committed to and leave a
        workspace the owner cannot remove. A failure here leaves an orphaned
        object that nothing references, which is the cheaper outcome.

        The site's favicon is stored in MinIO.

        ponytail: deletes inside the request, before the outer commit. If the
        commit then fails, the objects are gone and the rows are back. Move this
        to a post-commit sweep if that window ever matters.
        """
        if favicon_object:
            from src.services.workspace_favicon import delete_favicon

            await delete_favicon(favicon_object)  # best-effort; never raises

    async def get_deleted_workspace(self, workspace_id: UUID) -> WorkspaceModel:
        """
        Get a soft-deleted workspace by ID (used by the restore flow).

        Args:
            workspace_id: Workspace UUID

        Returns:
            WorkspaceModel object

        Raises:
            ResourceNotFoundException: If workspace not found or not deleted
        """
        result = await self.db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.deleted_at.is_not(None),
            )
        )
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise ResourceNotFoundException(
                resource_type="Workspace", resource_id=str(workspace_id)
            )

        return workspace

    async def restore_workspace(self, workspace_id: UUID, user_id: UUID) -> WorkspaceModel:
        """
        Restore a soft-deleted workspace within its 30-day recovery period.

        Business Rules:
        - Only the workspace owner can restore it
        - Only allowed within 30 days of deletion
        - Related data was never touched by the soft delete, so it's restored as-is

        Args:
            workspace_id: Workspace UUID
            user_id: User performing the restore

        Raises:
            ResourceNotFoundException: If workspace not found or not deleted
            RextValidationException: If the 30-day recovery window has passed
        """
        # Verify ownership first (role checks are independent of deleted_at)
        await self.verify_user_is_workspace_owner(workspace_id, user_id)

        workspace = await self.get_deleted_workspace(workspace_id)

        recovery_deadline = workspace.deleted_at + timedelta(days=30)
        if datetime.now(timezone.utc) > recovery_deadline:
            raise RextValidationException(
                message="The 30-day recovery period for this workspace has expired."
            )

        workspace.deleted_at = None
        workspace.deleted_by = None

        logger.info(
            "Workspace restored",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id)},
        )

        return workspace

    async def get_deleted_workspaces_for_user(self, user_id: UUID) -> List[WorkspaceModel]:
        """
        List the user's soft-deleted workspaces that are still within the
        30-day recovery window (i.e. actually restorable), newest deletion first.

        Ownership is checked the same way as delete/restore: via a
        workspace-scoped role at or above the workspace_owner hierarchy level,
        not WorkspaceModel.user_id (which reflects the creator, not necessarily
        the current owner after a transfer).

        Args:
            user_id: User UUID

        Returns:
            List of soft-deleted WorkspaceModel objects, most recently deleted first
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        result = await self.db.execute(
            select(WorkspaceModel)
            .join(
                UserRole,
                and_(
                    UserRole.workspace_id == WorkspaceModel.id,
                    UserRole.user_id == user_id,
                ),
            )
            .join(Role, UserRole.role_id == Role.id)
            .where(
                WorkspaceModel.deleted_at.is_not(None),
                WorkspaceModel.deleted_at > cutoff,
                Role.hierarchy_level >= 60,
            )
            .order_by(WorkspaceModel.deleted_at.desc())
        )
        return list(result.scalars().all())

    async def count_user_workspaces(self, user_id: UUID) -> int:
        """
        Count the number of active workspaces a user has access to.

        Args:
            user_id: User UUID

        Returns:
            Number of active workspaces
        """
        result = await self.db.execute(
            select(func.count(distinct(WorkspaceModel.id)))
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .where(WorkspaceMembers.user_id == user_id, WorkspaceModel.deleted_at.is_(None))
        )
        count = result.scalar() or 0
        return count

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _ensure_active_user(self, user_id: UUID) -> Users:
        result = await self.db.execute(
            select(Users).where(Users.id == user_id, Users.deleted_at.is_(None))
        )
        user = result.scalar_one_or_none()
        if not user:
            raise RextAuthenticationException(
                message="User not found",
                context={"user_id": str(user_id)},
            )
        return user

    async def _ensure_membership(self, workspace_id: UUID, user_id: UUID) -> WorkspaceModel:
        query = (
            select(WorkspaceModel)
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .where(
                WorkspaceModel.id == workspace_id,
                WorkspaceMembers.user_id == user_id,
            )
        )
        result = await self.db.execute(query)
        workspace = result.scalar_one_or_none()
        if not workspace:
            raise ResourceNotFoundException(
                resource_type="workspace",
                resource_id=str(workspace_id),
            )
        return workspace

    async def _get_workspace_owner_role(self) -> Role:
        """
        Get the workspace_owner role.

        This role is assigned to users who create a workspace, giving them
        full control including workspace deletion and billing management.

        Note: Uses is_workspace_role instead of is_system_role for proper
        role classification. workspace_owner is a workspace role, not a
        platform/system role.

        Returns:
            Role: The workspace_owner role

        Raises:
            ValueError: If workspace_owner role not found in database
        """
        result = await self.db.execute(
            select(Role).where(Role.name == "workspace_owner", Role.is_workspace_role)
        )
        role = result.scalar_one_or_none()

        if not role:
            raise ValueError(
                "Workspace role 'workspace_owner' not found. "
                "Please ensure role seeding migrations have been run."
            )

        return role

    async def _assign_permissions_to_role(self, role_id: UUID, resources: List[str]) -> None:
        if not resources:
            return
        result = await self.db.execute(select(Permission).where(Permission.resource.in_(resources)))
        permissions = result.scalars().all()

        if not permissions:
            return

        # Batch-query existing role-permission assignments to avoid N+1
        permission_ids = [p.id for p in permissions]
        existing_result = await self.db.execute(
            select(RolePermission.permission_id).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id.in_(permission_ids),
            )
        )
        existing_ids = {row[0] for row in existing_result.all()}

        for permission in permissions:
            if permission.id in existing_ids:
                continue
            self.db.add(RolePermission(role_id=role_id, permission_id=permission.id))

    async def _assign_role_to_user(self, role_id: UUID, user_id: UUID, workspace_id: UUID) -> None:
        result = await self.db.execute(
            select(UserRole).where(
                UserRole.role_id == role_id,
                UserRole.user_id == user_id,
                UserRole.workspace_id == workspace_id,
            )
        )
        if result.scalar_one_or_none():
            return

        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            workspace_id=workspace_id,
            is_primary=True,
        )
        self.db.add(user_role)

    async def _ensure_unique_workspace_name(self, name: str, user_id: UUID) -> None:
        result = await self.db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.name == name,
                WorkspaceModel.user_id == user_id,
            )
        )
        if result.scalar_one_or_none():
            raise DuplicateResourceException(
                message=f"Workspace with name '{name}' already exists",
                resource_type="workspace",
                conflicting_field="name",
                conflicting_value=name,
            )

    def _serialize_workspace(self, workspace: WorkspaceModel) -> Dict[str, Any]:
        return {
            "id": str(workspace.id),
            "user_id": str(workspace.user_id),
            "name": workspace.name,
            "slug": workspace.slug,
            "timezone": workspace.timezone,
            "url": workspace.url,
            "favicon_url": resolve_media_url(workspace.favicon_url),
            "pipeline": pipeline_state(workspace),
            "created_at": (workspace.created_at.isoformat() if workspace.created_at else None),
            "updated_at": (workspace.updated_at.isoformat() if workspace.updated_at else None),
        }

    def _slugify(self, text: str) -> str:
        """
        Convert text to URL-safe slug.

        Args:
            text: Text to slugify

        Returns:
            URL-safe slug
        """
        # Accented letters keep their base letter ("Café" is "cafe"), as an address needs.
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        text = text.lower()
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"[^a-z0-9-]", "", text)
        text = re.sub(r"-+", "-", text)
        # A name with no Latin letter or digit ("茶屋") leaves nothing, and still needs an address.
        text = text.strip("-") or "workspace"
        return text

    async def _generate_unique_slug(
        self, base_slug: str, user_id: UUID, exclude_id: Optional[UUID] = None
    ) -> str:
        """
        Generate unique slug globally (the DB constraint is a global unique index).

        Even though slugs are conceptually scoped per user, the database enforces
        a global unique constraint on the slug column (ix_workspace_slug). We must
        therefore check against all workspaces, not just those belonging to this user,
        to avoid IntegrityErrors at flush time.

        Args:
            base_slug: Base slug to make unique
            user_id: User UUID (unused for the uniqueness check but kept for
                     signature compatibility)
            exclude_id: Workspace ID to exclude from check (for updates)

        Returns:
            Globally unique slug
        """
        slug = base_slug
        counter = 1

        while True:
            # Check global uniqueness to match the DB-level unique constraint
            query = select(WorkspaceModel).where(WorkspaceModel.slug == slug)

            if exclude_id:
                query = query.where(WorkspaceModel.id != exclude_id)

            result = await self.db.execute(query)
            existing = result.scalar_one_or_none()

            if not existing:
                return slug

            slug = f"{base_slug}-{counter}"
            counter += 1
