from typing import Optional
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextAuthorizationException
from src.api.security.dependencies import get_current_user
from src.services.usage_tracking_service import UsageTrackingService
from src.utils.logger import logger


class RequireFeature:
    """
    FastAPI dependency that enforces server-side feature gating.

    Usage:
        @router.post("/workspaces", dependencies=[Depends(RequireFeature("workspaces"))])
        async def create_workspace(...):
            ...

    Or as a function parameter:
        @router.post("/workspaces")
        async def create_workspace(
            feature_check: bool = Depends(RequireFeature("workspaces")),
            ...
        ):
            ...
    """

    def __init__(self, limit_type: str, error_message: Optional[str] = None):
        """
        Args:
            limit_type: The usage limit to check (e.g., "workspaces", "members")
            error_message: Custom error message when limit is exceeded
        """
        self.limit_type = limit_type
        self.error_message = error_message

    async def __call__(
        self,
        request: Request,
        db: AsyncSession = Depends(get_async_db),
        current_user: dict = Depends(get_current_user),
    ) -> bool:
        """Check if the current user is within their plan limits."""
        # Get user_id from the authenticated request
        user_id = current_user.get("identity")
        if not user_id:
            raise RextAuthorizationException(
                message="Authentication required", required_permission=f"feature.{self.limit_type}"
            )

        # Store user_id in request state for other dependencies/handlers
        request.state.user_id = user_id

        usage_service = UsageTrackingService(db)

        try:
            usage = await usage_service.get_usage_metrics(UUID(str(user_id)))
        except Exception as e:
            logger.error(f"Feature gate check failed for user {user_id}: {e}")
            # Fail open for usage check errors to avoid blocking legitimate users
            # Log the error for monitoring
            return True

        # Check the specific limit
        metric = usage.get(self.limit_type, {})
        current = metric.get("used", 0) or 0
        limit = metric.get("limit")

        if limit is not None and limit > 0 and current >= limit:
            plan_name = usage.get("meta", {}).get("plan_name", "your current plan")
            message = self.error_message or (
                f"You have reached the {self.limit_type.replace('_', ' ')} limit "
                f"for {plan_name} ({current}/{limit}). "
                f"Please upgrade your plan to continue."
            )
            raise RextAuthorizationException(
                message=message, required_permission=f"feature.{self.limit_type}"
            )

        return True
