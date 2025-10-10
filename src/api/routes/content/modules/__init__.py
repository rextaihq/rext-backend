from fastapi import APIRouter
from .content_retrieval import router as retrieval_router
from .content_crud import router as crud_router
from .content_generation import router as generation_router

router = APIRouter(
    prefix="/content",
    tags=["content"],
    responses={404: {"description": "Not found"}},
)

router.include_router(retrieval_router)
router.include_router(crud_router)
router.include_router(generation_router)

__all__ = ["router"]
