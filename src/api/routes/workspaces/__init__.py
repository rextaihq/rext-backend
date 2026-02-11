from .workspace_core import (
    router as core_router,
    get_workspaces,
    get_workspace_by_slug,
    get_workspace_by_id_path,
    create_workspace,
    update_workspace,
    delete_workspace_endpoint,
    get_available_roles,
)
from .workspace_brand_voice import router as brand_voice_router
from .workspace_personas import router as personas_router
from .workspace_members import router as members_router
from .workspace_invitations import router as invitations_router
from .workspace_permissions import router as permissions_router
from .workspace_stats import router as stats_router
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import db_transaction_handler, require_permissions

from fastapi import APIRouter

# Add alias routes for frontend compatibility (plural "workspaces" vs singular "workspace")
# This allows the frontend to call either endpoint with RESTful conventions
workspaces_router = APIRouter(prefix="/workspaces", tags=["workspace"])
workspaces_router.include_router(brand_voice_router)
workspaces_router.include_router(personas_router)
workspaces_router.include_router(members_router)
workspaces_router.include_router(invitations_router)
workspaces_router.include_router(permissions_router)
workspaces_router.include_router(stats_router)

# GET endpoints - ORDER MATTERS! More specific routes must come before parameterized routes
workspaces_router.add_api_route("", get_workspaces, methods=["GET"], name="get_workspaces_alias")
workspaces_router.add_api_route("/slug/{workspace_slug}", get_workspace_by_slug, methods=["GET"], name="get_workspace_by_slug_alias")
# Note: /{workspace_id} must be added AFTER all other specific routes to avoid capturing them




# POST/PUT/DELETE endpoints - RESTful wrappers
workspaces_router.add_api_route("", create_workspace, methods=["POST"], name="create_workspace_restful")
workspaces_router.add_api_route("/{workspace_id}", update_workspace, methods=["PUT"], name="update_workspace_restful")
workspaces_router.add_api_route("/{workspace_id}", delete_workspace_endpoint, methods=["DELETE"], name="delete_workspace_restful")
workspaces_router.add_api_route("/available-roles", get_available_roles, methods=["GET"], name="get_available_roles")



# Add parameterized routes LAST to avoid capturing specific routes
workspaces_router.add_api_route("/{workspace_id}", get_workspace_by_id_path, methods=["GET"], name="get_workspace_by_id_restful")

__all__ = ["workspaces_router"]
