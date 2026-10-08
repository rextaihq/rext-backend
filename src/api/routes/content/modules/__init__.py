from fastapi import APIRouter

from .calendar import router as calendar_router
from .content_retrieval import router as retrieval_router
from .content_versions import router as versions_router
from .generation_webhook import router as generation_webhook_router
from .publish_content import router as publish_router

router = APIRouter(
    prefix="/content",
    tags=["content"],
    responses={404: {"description": "Not found"}},
)

router.include_router(calendar_router)  # static /calendar before /{content_id}
router.include_router(generation_webhook_router)  # static path, also before /{content_id}
router.include_router(retrieval_router)
router.include_router(publish_router)
router.include_router(versions_router)

__all__ = ["router"]
