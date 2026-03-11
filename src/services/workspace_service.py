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

from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime, timezone
import re
from asyncio import create_task

from sqlalchemy import select, func, distinct, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import expression
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.knowledge_models.knowledge_model import (
    Website,
    KnowledgeFiles,
    TextKnowledge,
    BrandVoice,
)
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.user_roles import UserRole
from src.api.models.content_models.content import Content
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
    DuplicateResourceException,
    RextAuthenticationException,
)
from src.api.schema.knowledge_schema import BrandSchema
from src.flow.model.llm_manager import load_model
from src.utils.helper import web_page_scraper
from src.utils.vector_store import add_to_vector_store, delete_vectors
from src.api.cache.decorators import cached
from src.utils.logger import logger
from src.api.database.async_database import get_async_db, get_async_db_context
from src.services.workspace_pipeline import run_workspace_pipeline
from src.services.sse_service import event_stream_manager
from langsmith import traceable, trace
import weakref

# Track background pipeline tasks to prevent garbage collection
_background_tasks: set = set()

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

    async def get_workspace_for_user(
        self, workspace_id: UUID, user_id: UUID
    ) -> Dict[str, Any]:
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
        url: str,
    ) -> Dict[str, Any]:
        """
        Create a workspace and trigger the background onboarding pipeline.

        Returns immediately with workspace metadata and an SSE operation ID.
        """
        await self._ensure_active_user(user_id)
        with trace(name="Create Workspace Record"):
            # TEMPORARY: Disable duplicate URL check for testing
            # result = await self.db.execute(
            #     select(Website)
            #     .join(WorkspaceModel, WorkspaceModel.id == Website.workspace_id)
            #     .where(
            #         WorkspaceModel.user_id == user_id,
            #         WorkspaceModel.deleted_at.is_(None),
            #         Website.url == url,
            #     )
            # )
            # if result.scalar_one_or_none():
            #     raise DuplicateResourceException(
            #         message="Workspace with this URL already exists",
            #         resource_type="workspace",
            #         conflicting_field="url",
            #         conflicting_value=url,
            #     )
            # else:
            workspace = await self.create_workspace(
                user_id=user_id, name=name, tz=timezone, url=url
            )
            await self.db.refresh(workspace)

        with trace(name="Assign Roles & Permissions"):
            await self.create_workspace_member(
                workspace.id, user_id, is_default=True, status="active"
            )
            owner_role = await self._get_workspace_owner_role()
            await self._assign_role_to_user(owner_role.id, user_id, workspace.id)

        operation_id = str(uuid4())

        # Register ownership so only this user can publish events to this operation
        await event_stream_manager.set_operation_owner(operation_id, user_id)

        async def run_pipeline() -> None:
            with trace(
                name="Run Workspace Pipeline",
                inputs={"operation_id": operation_id, "url": url},
            ):
                async with get_async_db_context() as bg_db:
                    try:
                        await run_workspace_pipeline(
                            db=bg_db,
                            operation_id=operation_id,
                            workspace_id=workspace.id,
                            user_id=user_id,
                            url=url,
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

        if not workspace.url:
            raise RextValidationException(
                message="Workspace URL is required to refresh brand voice",
                field_errors={
                    "url": ["Workspace must have a valid URL before refreshing"]
                },
            )

        operation_id = str(uuid4())

        # Register ownership so only this user can publish events to this operation
        await event_stream_manager.set_operation_owner(operation_id, user_id)

        async def run_pipeline() -> None:
            async with get_async_db_context() as bg_db:
                try:
                    await run_workspace_pipeline(
                        db=bg_db,
                        operation_id=operation_id,
                        workspace_id=workspace.id,
                        user_id=user_id,
                        url=workspace.url,
                    )
                except Exception as exc:
                    logger.error(
                        "Workspace refresh pipeline failed",
                        extra={
                            "operation_id": operation_id,
                            "workspace_id": str(workspace.id),
                            "error": str(exc),
                        },
                        exc_info=True,
                    )
                    raise

        task = create_task(run_pipeline())

        def handle_completion(pipeline_task) -> None:
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

    async def delete_workspace_for_user(
        self, workspace_id: UUID, user_id: UUID
    ) -> None:
        """Delete workspace after verifying membership and cleanup."""
        await self._ensure_active_user(user_id)
        workspace = await self._ensure_membership(workspace_id, user_id)
        self._delete_vectors_safe(workspace.id) 
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
        await self.db.refresh(updated)
        return self._serialize_workspace(updated)

    @cached(
        key_prefix="user:workspaces",
        ttl=300,
        key_builder=lambda self, user_id: str(user_id)
    )
    async def get_user_workspaces(self, user_id: UUID) -> List[Dict[str, Any]]:
        """
        Get all workspaces for a user with counts.

        Optimized query that fetches workspace data with knowledge and member counts
        in a single query.

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
                func.count(distinct(Website.id)).label("web_knowledge_count"),
                func.count(distinct(KnowledgeFiles.id)).label("files_count"),
                func.count(distinct(TextKnowledge.id)).label("text_knowledge_count"),
                func.count(distinct(WorkspaceMembers.id)).label("members_count"),
            )
            .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
            .join(Users, Users.id == WorkspaceModel.user_id)
            .outerjoin(Website, Website.workspace_id == WorkspaceModel.id)
            .outerjoin(KnowledgeFiles, KnowledgeFiles.workspace_id == WorkspaceModel.id)
            .outerjoin(TextKnowledge, TextKnowledge.workspace_id == WorkspaceModel.id)
            .where(
                WorkspaceMembers.user_id == user_id,
                WorkspaceModel.deleted_at.is_(
                    None
                ),  # Filter out soft-deleted workspaces
            )
            .group_by(WorkspaceModel.id, Users.id)
        )

        result = await self.db.execute(workspaces_query)
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

            workspace_data.append(
                {
                    "id": str(ws.id),
                    "user_id": str(ws.user_id),
                    "name": ws.name,
                    "slug": ws.slug,
                    "timezone": ws.timezone,
                    "url": ws.url,
                    "created_at": ws.created_at.isoformat() if ws.created_at else None,
                    "updated_at": ws.updated_at.isoformat() if ws.updated_at else None,
                    "owner": {"name": owner_name, "email": owner_email},
                    "knowledge_stats": {
                        "web_knowledge": web_count,
                        "files": files_count,
                        "text_knowledge": text_count,
                        "total": total_knowledge,
                    },
                    "members_count": members_count,
                    "status": "active",
                }
            )

        logger.info(
            "Retrieved workspaces for user",
            extra={"user_id": str(user_id), "count": len(workspace_data)},
        )

        return workspace_data

    async def get_workspace_analytics(
        self, workspace_id: UUID, include_word_counts: bool = False
    ) -> Dict[str, Any]:
        """
        Get comprehensive analytics for a workspace.

        Uses optimized queries to fetch knowledge counts, content counts,
        member counts, and optionally word counts.

        Args:
            workspace_id: Workspace UUID
            include_word_counts: Whether to include detailed word count analytics

        Returns:
            Dict with analytics data
        """
        # Get counts in separate queries (simplified version)
        # Combine all counts into a single query using scalar subqueries
        web_count_subq = (
            select(func.count(Website.id))
            .where(Website.workspace_id == workspace_id)
            .correlate(None)
            .scalar_subquery()
        )
        files_count_subq = (
            select(func.count(KnowledgeFiles.id))
            .where(KnowledgeFiles.workspace_id == workspace_id)
            .correlate(None)
            .scalar_subquery()
        )
        text_count_subq = (
            select(func.count(TextKnowledge.id))
            .where(TextKnowledge.workspace_id == workspace_id)
            .correlate(None)
            .scalar_subquery()
        )
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
                web_count_subq.label("web_count"),
                files_count_subq.label("files_count"),
                text_count_subq.label("text_count"),
                members_count_subq.label("members_count"),
                content_count_subq.label("content_count"),
            )
        )
        row = result.one()
        web_count = row.web_count or 0
        files_count = row.files_count or 0
        text_count = row.text_count or 0
        members_count = row.members_count or 0
        content_count = row.content_count or 0

        analytics = {
            "knowledge_stats": {
                "web_knowledge": web_count,
                "files": files_count,
                "text_knowledge": text_count,
                "total": web_count + files_count + text_count,
            },
            "members_count": members_count,
            "content_count": content_count,
        }

        # Add word count analytics if requested
        if include_word_counts:
            word_stats_query = select(
                func.coalesce(
                    select(func.sum(Website.word_count))
                    .where(Website.workspace_id == workspace_id)
                    .correlate(None)
                    .scalar_subquery(),
                    0,
                ).label("total_web_words"),
                func.coalesce(
                    select(func.avg(Website.word_count))
                    .where(Website.workspace_id == workspace_id)
                    .correlate(None)
                    .scalar_subquery(),
                    0,
                ).label("avg_web_words"),
                func.coalesce(
                    select(func.sum(KnowledgeFiles.word_count))
                    .where(KnowledgeFiles.workspace_id == workspace_id)
                    .correlate(None)
                    .scalar_subquery(),
                    0,
                ).label("total_file_words"),
                func.coalesce(
                    select(func.avg(KnowledgeFiles.word_count))
                    .where(KnowledgeFiles.workspace_id == workspace_id)
                    .correlate(None)
                    .scalar_subquery(),
                    0,
                ).label("avg_file_words"),
            )
            result = await self.db.execute(word_stats_query)
            word_row = result.one()

            total_web_words = int(word_row.total_web_words)
            avg_web_words = int(word_row.avg_web_words)
            total_file_words = int(word_row.total_file_words)
            avg_file_words = int(word_row.avg_file_words)

            total_words = total_web_words + total_file_words
            estimated_reading_time = total_words // 200

            analytics["content_metrics"] = {
                "total_words": total_words,
                "web_content_words": total_web_words,
                "file_content_words": total_file_words,
                "avg_web_article_words": avg_web_words,
                "avg_file_words": avg_file_words,
                "estimated_reading_time_minutes": estimated_reading_time,
            }

        logger.info(
            "Retrieved analytics for workspace",
            extra={
                "workspace_id": str(workspace_id),
                "total_knowledge": analytics["knowledge_stats"]["total"],
            },
        )

        return analytics

    @cached(
        key_prefix="workspace:brand_voice",
        ttl=600,
        key_builder=lambda self, workspace_id: str(workspace_id),
    )
    async def get_workspace_with_brand_voice(
        self, workspace_id: UUID
    ) -> Dict[str, Any]:
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
            "created_at": (
                workspace.created_at.isoformat() if workspace.created_at else None
            ),
            "updated_at": (
                workspace.updated_at.isoformat() if workspace.updated_at else None
            ),
        }

        # Add brand voice if exists
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
                "created_at": (
                    brand_voice.created_at.isoformat()
                    if brand_voice.created_at
                    else None
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
            select(WorkspaceModel).where(
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

    async def get_workspace_by_slug_for_user(
        self, slug: str, user_id: UUID
    ) -> WorkspaceModel:
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
                .join(
                    WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id
                )
                .where(
                    WorkspaceModel.id == UUID(identifier),
                    WorkspaceMembers.user_id == user_id,
                    WorkspaceModel.deleted_at.is_(None),
                )
            )
        else:
            query = (
                select(WorkspaceModel)
                .join(
                    WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id
                )
                .where(
                    WorkspaceModel.slug == identifier,
                    WorkspaceMembers.user_id == user_id,
                    WorkspaceModel.deleted_at.is_(None),
                )
            )

        result = await self.db.execute(query)
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise ResourceNotFoundException(
                resource_type="workspace", resource_id=identifier
            )

        return workspace

    async def verify_user_is_workspace_owner(
        self, workspace_id: UUID, user_id: UUID
    ) -> bool:
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
                Role.hierarchy_level >= 60, # workspace_owner or higher (60 is workspace_owner)
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
        
        from src.api.cache.decorators import invalidate_cache_key
        await invalidate_cache_key(f"user:workspaces:{user_id}")

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

        from src.api.cache.decorators import invalidate_cache_key
        await invalidate_cache_key(f"user:workspaces:{user_id}")

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
            workspace.name = name
            # Regenerate slug if name changed
            base_slug = self._slugify(name)
            workspace.slug = await self._generate_unique_slug(
                base_slug, workspace.user_id, exclude_id=workspace_id
            )

        if tz is not None:
            workspace.timezone = tz

        if url is not None:
            workspace.url = url

        workspace.updated_at = datetime.now(timezone.utc)

        logger.info(
            "Workspace updated",
            extra={"workspace_id": str(workspace_id)},
        )

        from src.api.cache.decorators import invalidate_cache_key
        await invalidate_cache_key(f"user:workspaces:{workspace.user_id}")

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
        await self.verify_user_is_workspace_owner(workspace_id, user_id )
         
        workspace = await self.get_workspace(workspace_id)

        # Soft delete: set deleted_at and deleted_by
        workspace.deleted_at = datetime.now(timezone.utc)
        workspace.deleted_by = user_id

        logger.info(
            "Workspace soft deleted",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id)},
        )
        
        from src.api.cache.decorators import invalidate_cache_key
        await invalidate_cache_key(f"user:workspaces:{user_id}")

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
            .where(
                WorkspaceMembers.user_id == user_id, WorkspaceModel.deleted_at.is_(None)
            )
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

    async def _ensure_membership(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceModel:
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
            select(Role).where(
                Role.name == "workspace_owner", Role.is_workspace_role == True
            )
        )
        role = result.scalar_one_or_none()

        if not role:
            raise ValueError(
                "Workspace role 'workspace_owner' not found. "
                "Please ensure role seeding migrations have been run."
            )

        return role

    async def _assign_permissions_to_role(
        self, role_id: UUID, resources: List[str]
    ) -> None:
        if not resources:
            return
        result = await self.db.execute(
            select(Permission).where(Permission.resource.in_(resources))
        )
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

    async def _assign_role_to_user(
        self, role_id: UUID, user_id: UUID, workspace_id: UUID
    ) -> None:
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

    async def _populate_brand_voice_and_vectors(
        self, workspace_id: UUID, url: Optional[str]
    ) -> None:
        if not url:
            return

        chunks = []
        content = ""

        try:
            scraped_chunks, results = await web_page_scraper(urls=[url])
            chunks = scraped_chunks or []
            if results:
                first = results[0]
                content = first.markdown if getattr(first, "success", False) else ""
        except Exception as scrape_err:  # noqa: BLE001
            logger.warning(
                "Workspace scraping failed",
                extra={"workspace_id": str(workspace_id), "error": str(scrape_err)},
            )

        try:
            if chunks:
                add_to_vector_store(blog_context=chunks, workspace_id=str(workspace_id))
        except Exception as vector_err:  # noqa: BLE001
            logger.warning(
                "Vector store update failed",
                extra={"workspace_id": str(workspace_id), "error": str(vector_err)},
            )

        if not content:
            return

        try:
            model = load_model()
            structure_model = model.with_structured_output(BrandSchema)
            brand_data = await structure_model.ainvoke(content)

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
            self.db.add(brand_voice)
            await self.db.flush()
        except Exception as llm_err:  # noqa: BLE001
            logger.warning(
                "Brand voice generation failed",
                extra={"workspace_id": str(workspace_id), "error": str(llm_err)},
            )

    def _delete_vectors_safe(self, workspace_id: UUID) -> None:
        try:
            delete_vectors(vector_id=str(workspace_id))
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "Vector cleanup failed",
                extra={"workspace_id": str(workspace_id), "error": str(err)},
            )

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
            "created_at": (
                workspace.created_at.isoformat() if workspace.created_at else None
            ),
            "updated_at": (
                workspace.updated_at.isoformat() if workspace.updated_at else None
            ),
        }

    def _slugify(self, text: str) -> str:
        """
        Convert text to URL-safe slug.

        Args:
            text: Text to slugify

        Returns:
            URL-safe slug
        """
        text = text.lower()
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"[^a-z0-9-]", "", text)
        text = re.sub(r"-+", "-", text)
        text = text.strip("-")
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