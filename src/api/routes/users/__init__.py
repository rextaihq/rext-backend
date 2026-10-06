from fastapi import APIRouter

from . import (
    auth,
    impersonation,
    invitations,
    management,
    password,
    preferences,
    profile,
    roles,
    sessions,
    status,
    user_permissions,
    user_security,
    user_status,
)

# Create main router with prefix and tags
router = APIRouter(prefix="/user", tags=["user"])

# Include all sub-routers without additional prefixes
router.include_router(status.router)
router.include_router(auth.router)
router.include_router(password.router)
router.include_router(profile.router)
router.include_router(sessions.router)
router.include_router(management.router)
router.include_router(roles.router)
router.include_router(user_status.router)
router.include_router(impersonation.router)
router.include_router(user_permissions.router)
router.include_router(user_security.router)
router.include_router(preferences.router)
router.include_router(invitations.router)
