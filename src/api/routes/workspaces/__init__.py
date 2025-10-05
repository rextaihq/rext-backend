from fastapi import APIRouter
from .workspace_core import router as core_router
from .workspace_members import router as members_router
from .workspace_knowledge import router as knowledge_router
from .workspace_brand_voice import router as brand_voice_router

router = APIRouter(prefix="/workspace", tags=["workspace"])

router.include_router(core_router)
router.include_router(members_router)
router.include_router(knowledge_router)
router.include_router(brand_voice_router)

__all__ = ["router"]
