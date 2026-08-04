from fastapi import APIRouter

from .workspace_core import router as core_router
from .workspace_brand_voice import router as brand_voice_router
from .workspace_personas import router as personas_router
from .workspace_audiences import router as audiences_router
from .workspace_members import router as members_router
from .workspace_invitations import router as invitations_router, singular_router as singular_invitations_router
from .workspace_permissions import router as permissions_router
from .workspace_stats import router as stats_router

# Orchestrator router for plural "/workspaces" endpoints
workspaces_router = APIRouter(prefix="/workspaces", tags=["workspaces"])

# Include the core CRUD operations
workspaces_router.include_router(core_router)

# Include specialized sub-routers
workspaces_router.include_router(brand_voice_router)
workspaces_router.include_router(personas_router)
workspaces_router.include_router(audiences_router)
workspaces_router.include_router(members_router)
workspaces_router.include_router(invitations_router)
workspaces_router.include_router(permissions_router)
workspaces_router.include_router(stats_router)

# Singular router for frontend parity (TASK-336)
workspace_router = APIRouter(prefix="/workspace", tags=["workspace"])
workspace_router.include_router(singular_invitations_router)

__all__ = ["workspaces_router", "workspace_router"]
