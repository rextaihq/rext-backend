from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.roles import Role
from src.utils.db_utils import get_or_404

__all__ = ['verify_workspace_exists', 'verify_role_exists']


async def verify_workspace_exists(db: AsyncSession, workspace_id: UUID) -> WorkspaceModel:
    """
    Verify workspace exists and return it.
    Uses centralized get_or_404 utility.
    """
    return await get_or_404(db, WorkspaceModel, workspace_id, "workspace")


async def verify_role_exists(db: AsyncSession, role_id: UUID) -> Role:
    """
    Verify role exists and return it.
    Uses centralized get_or_404 utility.
    """
    return await get_or_404(db, Role, role_id, "role")
