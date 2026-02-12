
from typing import Optional, Callable
from uuid import UUID
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.services.usage_tracking_service import UsageTrackingService
from src.api.middleware.exceptions import RextAuthorizationException
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
            limit_type: The usage limit to check (e.g., "workspaces", "knowledge_items", "api_calls")
            error_message: Custom error message when limit is exceeded
        """
        self.limit_type = limit_type
        self.error_message = error_message

    async def __call__(
        self,
        request: Request,
        db: AsyncSession = Depends(get_async_db),
    ) -> bool:
        """Check if the current user is within their plan limits."""
        # Get user_id from the authenticated request
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise RextAuthorizationException(
                message="Authentication required",
                required_permission=f"feature.{self.limit_type}"
            )

        usage_service = UsageTrackingService(db)

        try:
            usage = await usage_service.get_usage_metrics(UUID(str(user_id)))
        except Exception as e:
            logger.error(f"Feature gate check failed for user {user_id}: {e}")
            # Fail open for usage check errors to avoid blocking legitimate users
            # Log the error for monitoring
            return True

        # Check the specific limit
        current_key = f"current_{self.limit_type}"
        max_key = f"max_{self.limit_type}"

        # Handle api_calls separately (different key naming)
        if self.limit_type == "api_calls":
            current = usage.get("current_api_calls", 0) or 0
            limit = usage.get("max_api_calls_per_month", 0)
        else:
            current = usage.get(current_key, 0) or 0
            limit = usage.get(max_key, 0)

        if limit is not None and limit > 0 and current >= limit:
            plan_name = usage.get("plan_name", "your current plan")
            message = self.error_message or (
                f"You have reached the {self.limit_type.replace('_', ' ')} limit "
                f"for {plan_name} ({current}/{limit}). "
                f"Please upgrade your plan to continue."
            )
            raise RextAuthorizationException(
                message=message,
                required_permission=f"feature.{self.limit_type}"
            )

        return True