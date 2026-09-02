from fastapi import APIRouter

from .calendar import router as calendar_router
from .content_retrieval import router as retrieval_router
from .publish_content import router as publish_router
from .sites import router as sites_router

router = APIRouter(
    prefix="/content",
    tags=["content"],
    responses={404: {"description": "Not found"}},
)

router.include_router(calendar_router)  # static /calendar before /{content_id}
router.include_router(retrieval_router)
router.include_router(publish_router)
router.include_router(sites_router, prefix="/sites")

__all__ = ["router"]
