from .sse_routes import router
from .sse_test_route import router as test_router

router.include_router(test_router)

__all__ = ["router"]
