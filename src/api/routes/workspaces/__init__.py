from fastapi import APIRouter
from .workspace_core import router as core_router, get_workspaces, get_workspace_by_slug
from .workspace_members import router as members_router
from .workspace_knowledge import router as knowledge_router
from .workspace_brand_voice import router as brand_voice_router

router = APIRouter(prefix="/workspace", tags=["workspace"])

router.include_router(core_router)
router.include_router(members_router)
router.include_router(knowledge_router)
router.include_router(brand_voice_router)

# Add alias routes for frontend compatibility (plural "workspaces" vs singular "workspace")
# This allows the frontend to call either endpoint
workspaces_router = APIRouter(prefix="/workspaces", tags=["workspace"])
workspaces_router.add_api_route("", get_workspaces, methods=["GET"], name="get_workspaces_alias")
workspaces_router.add_api_route("/slug/{workspace_slug}", get_workspace_by_slug, methods=["GET"], name="get_workspace_by_slug_alias")

__all__ = ["router", "workspaces_router"]
