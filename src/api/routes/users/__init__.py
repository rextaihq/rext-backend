from fastapi import APIRouter
from . import (
    status,
    auth,
    password,
    profile,
    sessions,
    management,
    roles,
    user_status,
    admin,
    impersonation
)

# Create main router with prefix and tags
router = APIRouter(
    prefix="/user",
    tags=["user"]
)

# Include all sub-routers without additional prefixes
router.include_router(status.router)
router.include_router(auth.router)
router.include_router(password.router)
router.include_router(profile.router)
router.include_router(sessions.router)
router.include_router(management.router)
router.include_router(roles.router)
router.include_router(user_status.router)
router.include_router(admin.router)
router.include_router(impersonation.router)
