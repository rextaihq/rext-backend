"""
Knowledge Base Service - Business Logic for Knowledge Base Operations

This service handles CRUD operations for knowledge bases, which group
knowledge items (web, file, text) together.

Responsibilities:
- Create, read, update, delete knowledge bases
- List knowledge bases for a workspace
- Get knowledge base with items count
- Manage default vs custom knowledge bases

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Authentication/authorization (that's decorators)
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.knowledge_models.knowledge_model import (
    KnowledgeBase,
)
from src.utils.logger import logger


class KnowledgeBaseService:
    """Service for knowledge base business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize KnowledgeBaseService.

        Args:
            db: Async database session
        """
        self.db = db

    async def create_knowledge_base(
        self, workspace_id: UUID, name: str, description: Optional[str] = None
    ) -> KnowledgeBase:
        """
        Create a new knowledge base for a workspace.

        Args:
            workspace_id: Workspace UUID
            name: Knowledge base name
            description: Optional description

        Returns:
            Created KnowledgeBase object

        Raises:
            DuplicateResourceException: If knowledge base with same name exists
        """
        # Check for duplicate name in workspace
        result = await self.db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.workspace_id == workspace_id, KnowledgeBase.name == name
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise DuplicateResourceException(
                resource_type="KnowledgeBase",
                conflicting_field="name",
                conflicting_value=name,
                message=f"Knowledge base with name '{name}' already exists in this workspace",
            )

        # Create knowledge base
        knowledge_base = KnowledgeBase(
            workspace_id=workspace_id, name=name, description=description, type="custom"
        )
        self.db.add(knowledge_base)
        await self.db.flush()
        await self.db.refresh(knowledge_base)

        logger.info(
            f"Knowledge base created: {knowledge_base.id}",
            extra={"workspace_id": str(workspace_id), "name": name},
        )

        return knowledge_base

    async def list_knowledge_bases(
        self,
        workspace_id: UUID,
        include_items_count: bool = True,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        List paginated knowledge bases for a workspace.

        Args:
            workspace_id: Workspace UUID
            include_items_count: Whether to include items count
            limit: Maximum number of items to return (default 20)
            offset: Number of items to skip (default 0)

        Returns:
            Tuple of (list of knowledge base dicts, total count)
        """

        # Get total count
        count_result = await self.db.execute(
            select(func.count())
            .select_from(KnowledgeBase)
            .where(KnowledgeBase.workspace_id == workspace_id)
        )
        total_count = count_result.scalar()

        # Build query
        query = (
            select(KnowledgeBase)
            .where(KnowledgeBase.workspace_id == workspace_id)
            .order_by(KnowledgeBase.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if include_items_count:
            query = query.options(
                selectinload(KnowledgeBase.websites),
                selectinload(KnowledgeBase.knowledge_files),
                selectinload(KnowledgeBase.text_knowledge),
            )

        result = await self.db.execute(query)
        knowledge_bases = result.scalars().all()
        items = [kb.to_dict() for kb in knowledge_bases]

        return items, total_count

    async def get_knowledge_base(
        self, workspace_id: UUID, knowledge_base_id: UUID, include_items: bool = False
    ) -> Dict[str, Any]:
        """
        Get a single knowledge base by ID.

        Args:
            workspace_id: Workspace UUID (for verification)
            knowledge_base_id: Knowledge base UUID
            include_items: Whether to include full knowledge items

        Returns:
            Knowledge base dictionary

        Raises:
            ResourceNotFoundException: If knowledge base not found
        """
        query = select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id, KnowledgeBase.workspace_id == workspace_id
        )

        if include_items:
            query = query.options(
                selectinload(KnowledgeBase.websites),
                selectinload(KnowledgeBase.knowledge_files),
                selectinload(KnowledgeBase.text_knowledge),
            )

        result = await self.db.execute(query)
        knowledge_base = result.scalar_one_or_none()

        if not knowledge_base:
            raise ResourceNotFoundException(
                resource_type="KnowledgeBase", resource_id=str(knowledge_base_id)
            )

        data = knowledge_base.to_dict()

        if include_items:
            data["websites"] = [w.to_dict() for w in knowledge_base.websites]
            data["knowledge_files"] = [kf.to_dict() for kf in knowledge_base.knowledge_files]
            data["text_knowledge"] = [tk.to_dict() for tk in knowledge_base.text_knowledge]

        return data

    async def update_knowledge_base(
        self,
        workspace_id: UUID,
        knowledge_base_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update a knowledge base.

        Args:
            workspace_id: Workspace UUID (for verification)
            knowledge_base_id: Knowledge base UUID
            name: Optional new name
            description: Optional new description

        Returns:
            Updated knowledge base dictionary

        Raises:
            ResourceNotFoundException: If knowledge base not found
            RextValidationException: If trying to update default knowledge base name
            DuplicateResourceException: If new name already exists
        """
        # Get knowledge base
        result = await self.db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id, KnowledgeBase.workspace_id == workspace_id
            )
        )
        knowledge_base = result.scalar_one_or_none()

        if not knowledge_base:
            raise ResourceNotFoundException(
                resource_type="KnowledgeBase", resource_id=str(knowledge_base_id)
            )

        # Prevent renaming default knowledge base
        if knowledge_base.type == "default" and name and name != knowledge_base.name:
            raise RextValidationException(
                message="Cannot rename the default knowledge base",
                field_errors={"name": ["Default knowledge base name cannot be changed"]},
            )

        # Check for duplicate name if updating name
        if name and name != knowledge_base.name:
            result = await self.db.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.workspace_id == workspace_id,
                    KnowledgeBase.name == name,
                    KnowledgeBase.id != knowledge_base_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                raise DuplicateResourceException(
                    resource_type="KnowledgeBase",
                    conflicting_field="name",
                    conflicting_value=name,
                    message=f"Knowledge base with name '{name}' already exists",
                )
            knowledge_base.name = name

        if description is not None:
            knowledge_base.description = description

        await self.db.flush()
        await self.db.refresh(knowledge_base)

        logger.info(
            "Knowledge base updated",
            extra={"workspace_id": str(workspace_id), "knowledge_base_id": str(knowledge_base_id)},
        )

        return knowledge_base.to_dict()

    async def delete_knowledge_base(self, workspace_id: UUID, knowledge_base_id: UUID) -> None:
        """
        Delete a knowledge base and all its knowledge items.

        Args:
            workspace_id: Workspace UUID (for verification)
            knowledge_base_id: Knowledge base UUID

        Raises:
            ResourceNotFoundException: If knowledge base not found
            RextValidationException: If trying to delete default knowledge base
        """
        # Get knowledge base
        result = await self.db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id, KnowledgeBase.workspace_id == workspace_id
            )
        )
        knowledge_base = result.scalar_one_or_none()

        if not knowledge_base:
            raise ResourceNotFoundException(
                resource_type="KnowledgeBase", resource_id=str(knowledge_base_id)
            )

        # Prevent deletion of default knowledge base
        if knowledge_base.type == "default":
            raise RextValidationException(
                message="Cannot delete the default knowledge base",
                field_errors={"knowledge_base_id": ["Default knowledge base cannot be deleted"]},
            )

        # Delete knowledge base (cascade will delete all items)
        await self.db.delete(knowledge_base)

        logger.info(
            f"Knowledge base deleted: {knowledge_base_id}",
            extra={"workspace_id": str(workspace_id)},
        )

    async def get_default_knowledge_base(self, workspace_id: UUID) -> KnowledgeBase:
        """
        Get or create the default knowledge base for a workspace.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Default KnowledgeBase object
        """
        # Try to get existing default knowledge base
        result = await self.db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.workspace_id == workspace_id, KnowledgeBase.type == "default"
            )
        )
        knowledge_base = result.scalar_one_or_none()

        # Create if doesn't exist
        if not knowledge_base:
            knowledge_base = KnowledgeBase(
                workspace_id=workspace_id,
                name="Default Knowledge Base",
                description="Automatically created default knowledge base",
                type="default",
            )
            self.db.add(knowledge_base)
            await self.db.flush()
            await self.db.refresh(knowledge_base)

            logger.info(
                f"Default knowledge base created: {knowledge_base.id}",
                extra={"workspace_id": str(workspace_id)},
            )

        return knowledge_base
