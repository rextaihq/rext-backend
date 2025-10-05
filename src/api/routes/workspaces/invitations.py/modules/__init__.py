from fastapi import APIRouter
from .invitation_create import router as create_router
from .invitation_manage import router as manage_router
from .invitation_list import router as list_router

router = APIRouter(
    prefix="/workspace/invitations",
    tags=["workspace", "invitations"],
    responses={404: {"description": "Not found"}},
)

router.include_router(create_router)
router.include_router(manage_router)
router.include_router(list_router)

__all__ = ["router"]
