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
from uuid import UUID
from datetime import datetime, timezone
import re

from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.knowledge_models.knowledge_model import Website, KnowledgeFiles, TextKnowledge
from src.api.models.user_models.users import Users
from src.api.models.content_models.content import Content
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException,
    DuplicateResourceException
)


class WorkspaceService:
    """Service for workspace business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize WorkspaceService.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_user_workspaces(
        self,
        user_id: UUID
    ) -> List[Dict[str, Any]]:
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

        logger.info(
            f"Retrieved {len(workspace_data)} workspaces for user",
            extra={"user_id": str(user_id), "count": len(workspace_data)}
        )

        return workspace_data

    async def get_workspace_analytics(
        self,
        workspace_id: UUID
    ) -> Dict[str, Any]:
        """
        Get comprehensive analytics for a workspace.

        Uses optimized queries to fetch knowledge counts, content counts,
        and member counts.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Dict with analytics data
        """
        # Get counts in separate queries (simplified version)
        result = await self.db.execute(
            select(func.count(Website.id)).where(Website.workspace_id == workspace_id)
        )
        web_count = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(KnowledgeFiles.id)).where(KnowledgeFiles.workspace_id == workspace_id)
        )
        files_count = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(TextKnowledge.id)).where(TextKnowledge.workspace_id == workspace_id)
        )
        text_count = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(WorkspaceMembers.id)).where(WorkspaceMembers.workspace_id == workspace_id)
        )
        members_count = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(Content.id)).where(
                Content.workspace_id == workspace_id,
                Content.deleted_at == None
            )
        )
        content_count = result.scalar() or 0

        analytics = {
            "knowledge_stats": {
                "web_knowledge": web_count,
                "files": files_count,
                "text_knowledge": text_count,
                "total": web_count + files_count + text_count
            },
            "members_count": members_count,
            "content_count": content_count
        }

        logger.info(
            f"Retrieved analytics for workspace",
            extra={"workspace_id": str(workspace_id), "total_knowledge": analytics["knowledge_stats"]["total"]}
        )

        return analytics

    async def get_workspace(
        self,
        workspace_id: UUID
    ) -> WorkspaceModel:
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
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise ResourceNotFoundException(
                resource_type="Workspace",
                resource_id=str(workspace_id)
            )

        return workspace

    async def create_workspace(
        self,
        user_id: UUID,
        name: str,
        description: Optional[str] = None,
        url: Optional[str] = None
    ) -> WorkspaceModel:
        """
        Create new workspace with owner membership.

        Business Rules:
        - Workspace name must be unique per user
        - Slug is auto-generated from name
        - Creator is automatically added as owner

        Args:
            user_id: User UUID (owner)
            name: Workspace name
            description: Workspace description
            url: Workspace URL

        Returns:
            Created WorkspaceModel object

        Raises:
            DuplicateResourceException: If workspace name already exists for user
        """
        # Generate unique slug
        base_slug = self._slugify(name)
        unique_slug = await self._generate_unique_slug(base_slug, user_id)

        # Create workspace
        workspace = WorkspaceModel(
            user_id=user_id,
            name=name,
            slug=unique_slug,
            description=description,
            url=url,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self.db.add(workspace)
        await self.db.flush()

        logger.info(
            f"Workspace created: {workspace.id}",
            extra={"user_id": str(user_id), "name": name}
        )

        return workspace

    async def update_workspace(
        self,
        workspace_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        url: Optional[str] = None
    ) -> WorkspaceModel:
        """
        Update workspace details.

        Args:
            workspace_id: Workspace UUID
            name: New workspace name (optional)
            description: New description (optional)
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
            workspace.slug = await self._generate_unique_slug(base_slug, workspace.user_id, exclude_id=workspace_id)

        if description is not None:
            workspace.description = description

        if url is not None:
            workspace.url = url

        workspace.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"Workspace updated: {workspace_id}",
            extra={"workspace_id": str(workspace_id)}
        )

        return workspace

    async def delete_workspace(
        self,
        workspace_id: UUID
    ) -> None:
        """
        Delete workspace and all related data.

        Business Rules:
        - Cascading delete of all workspace data (handled by DB)
        - Only workspace owner can delete

        Args:
            workspace_id: Workspace UUID

        Raises:
            ResourceNotFoundException: If workspace not found
        """
        workspace = await self.get_workspace(workspace_id)

        await self.db.delete(workspace)

        logger.info(
            f"Workspace deleted: {workspace_id}",
            extra={"workspace_id": str(workspace_id)}
        )

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _slugify(self, text: str) -> str:
        """
        Convert text to URL-safe slug.

        Args:
            text: Text to slugify

        Returns:
            URL-safe slug
        """
        text = text.lower()
        text = re.sub(r'[\s_]+', '-', text)
        text = re.sub(r'[^a-z0-9-]', '', text)
        text = re.sub(r'-+', '-', text)
        text = text.strip('-')
        return text

    async def _generate_unique_slug(
        self,
        base_slug: str,
        user_id: UUID,
        exclude_id: Optional[UUID] = None
    ) -> str:
        """
        Generate unique slug for user's workspaces.

        Args:
            base_slug: Base slug to make unique
            user_id: User UUID (slug unique per user)
            exclude_id: Workspace ID to exclude from check (for updates)

        Returns:
            Unique slug
        """
        slug = base_slug
        counter = 1

        while True:
            query = select(WorkspaceModel).where(
                WorkspaceModel.user_id == user_id,
                WorkspaceModel.slug == slug
            )

            if exclude_id:
                query = query.where(WorkspaceModel.id != exclude_id)

            result = await self.db.execute(query)
            existing = result.scalar_one_or_none()

            if not existing:
                return slug

            slug = f"{base_slug}-{counter}"
            counter += 1
