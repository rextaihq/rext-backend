"""
General API rate limiting middleware.

This module provides IP-based and user-based rate limiting to prevent API abuse.
Uses in-memory storage with sliding window algorithm.

Note: This is different from usage_limiter.py which enforces subscription-based
resource limits. This middleware protects against API abuse and DDoS attacks.

Usage:
    from src.api.middleware.rate_limiter import RateLimiterMiddleware

    app.add_middleware(
        RateLimiterMiddleware,
        requests_per_minute=60,
        requests_per_hour=1000
    )
"""

from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException, status, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
from collections import defaultdict, deque
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.utils.logger import logger
from src.api.security.dependencies import get_current_user


class RateLimiter:
    """
    Sliding window rate limiter.

    Tracks requests in a time window and enforces limits.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        requests_per_day: int = 10000
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute (default: 60)
            requests_per_hour: Maximum requests per hour (default: 1000)
            requests_per_day: Maximum requests per day (default: 10000)
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.requests_per_day = requests_per_day

        # Storage: {client_key: deque of timestamps}
        self.requests: Dict[str, deque] = defaultdict(deque)

        logger.info(
            f"Rate limiter initialized: "
            f"{requests_per_minute}/min, {requests_per_hour}/hour, {requests_per_day}/day"
        )

    def _cleanup_old_requests(self, timestamps: deque, window_seconds: int) -> None:
        """
        Remove timestamps older than the window.

        Args:
            timestamps: Deque of request timestamps
            window_seconds: Time window in seconds
        """
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)

        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

    def check_rate_limit(
        self,
        client_key: str
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Check if request is within rate limits.

        Args:
            client_key: Unique identifier for the client (IP or user ID)

        Returns:
            Tuple of (is_allowed, retry_after_seconds, limit_type)
        """
        now = datetime.utcnow()
        timestamps = self.requests[client_key]

        # Check minute limit
        self._cleanup_old_requests(timestamps, 60)
        if len(timestamps) >= self.requests_per_minute:
            oldest = timestamps[0]
            retry_after = int((oldest + timedelta(seconds=60) - now).total_seconds()) + 1
            return False, retry_after, "minute"

        # Check hour limit
        self._cleanup_old_requests(timestamps, 3600)
        if len(timestamps) >= self.requests_per_hour:
            oldest = timestamps[0]
            retry_after = int((oldest + timedelta(seconds=3600) - now).total_seconds()) + 1
            return False, retry_after, "hour"

        # Check day limit
        self._cleanup_old_requests(timestamps, 86400)
        if len(timestamps) >= self.requests_per_day:
            oldest = timestamps[0]
            retry_after = int((oldest + timedelta(seconds=86400) - now).total_seconds()) + 1
            return False, retry_after, "day"

        # Record this request
        timestamps.append(now)

        return True, None, None

    def get_client_key(self, request: Request) -> str:
        """
        Generate a unique key for the client.

        Prefers user ID if authenticated, falls back to IP address.

        Args:
            request: FastAPI request object

        Returns:
            Unique client identifier
        """
        # Try to get user ID from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"

        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"

        # Handle proxied requests
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        return f"ip:{client_ip}"

    def cleanup_old_entries(self) -> int:
        """
        Clean up stale entries to prevent memory growth.

        Removes entries with no requests in the last 24 hours.

        Returns:
            Number of entries removed
        """
        cutoff = datetime.utcnow() - timedelta(hours=24)
        keys_to_remove = []

        for key, timestamps in self.requests.items():
            if not timestamps or timestamps[-1] < cutoff:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.requests[key]

        if keys_to_remove:
            logger.info(f"Rate limiter cleanup: removed {len(keys_to_remove)} stale entries")

        return len(keys_to_remove)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting requests.

    Applies rate limits to all incoming requests based on IP or user ID.
    """

    # Paths exempt from rate limiting (health checks, docs, monitoring, etc.)
    EXEMPT_PATHS = {
        "/",
        "/health",
        "/health/live",
        "/health/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/status",
        # LangGraph Studio polling endpoints
        "/ok",
        "/info"
    }

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        requests_per_day: int = 10000,
        enable: bool = True
    ):
        """
        Initialize rate limiter middleware.

        Args:
            app: FastAPI application
            requests_per_minute: Max requests per minute (default: 60)
            requests_per_hour: Max requests per hour (default: 1000)
            requests_per_day: Max requests per day (default: 10000)
            enable: Whether to enable rate limiting (default: True)
        """
        super().__init__(app)
        self.limiter = RateLimiter(
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
            requests_per_day=requests_per_day
        )
        self.enable = enable
        self.cleanup_counter = 0

        if not enable:
            logger.warning("Rate limiting is DISABLED")

    async def dispatch(self, request: Request, call_next):
        """
        Process request and apply rate limiting.

        Args:
            request: Incoming request
            call_next: Next middleware in chain

        Returns:
            Response from next middleware or rate limit error

        Raises:
            HTTPException: If rate limit exceeded
        """
        # Skip if disabled
        if not self.enable:
            return await call_next(request)

        # Skip exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Get client identifier
        client_key = self.limiter.get_client_key(request)

        # Check rate limit
        is_allowed, retry_after, limit_type = self.limiter.check_rate_limit(client_key)

        if not is_allowed:
            logger.warning(
                f"Rate limit exceeded for {client_key}: {limit_type} limit reached. "
                f"Retry after {retry_after}s"
            )

            # Add rate limit headers
            headers = {
                "X-RateLimit-Limit": str(getattr(self.limiter, f"requests_per_{limit_type}")),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(retry_after),
                "Retry-After": str(retry_after)
            }

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Too many requests per {limit_type}. Try again in {retry_after} seconds.",
                headers=headers
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to successful responses
        if limit_type is None:  # Request was allowed
            # Calculate remaining for current minute
            client_key = self.limiter.get_client_key(request)
            timestamps = self.limiter.requests.get(client_key, deque())
            self.limiter._cleanup_old_requests(timestamps, 60)

            remaining = max(0, self.limiter.requests_per_minute - len(timestamps))

            response.headers["X-RateLimit-Limit"] = str(self.limiter.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        # Periodic cleanup (every 1000 requests)
        self.cleanup_counter += 1
        if self.cleanup_counter >= 1000:
            self.limiter.cleanup_old_entries()
            self.cleanup_counter = 0

        return response


# ============================================================================
# ENDPOINT-SPECIFIC RATE LIMITERS (Dependency Injection)
# ============================================================================

class EndpointRateLimiter:
    """
    Rate limiter for specific endpoints (via dependency injection).

    More strict limits for sensitive endpoints like login, password reset, etc.
    """

    def __init__(
        self,
        requests: int = 5,
        window_minutes: int = 1,
        description: str = "endpoint"
    ):
        """
        Initialize endpoint-specific rate limiter.

        Args:
            requests: Maximum requests allowed in the window
            window_minutes: Time window in minutes
            description: Description for error messages
        """
        self.requests = requests
        self.window_seconds = window_minutes * 60
        self.description = description
        self.storage: Dict[str, deque] = defaultdict(deque)

    async def __call__(self, request: Request):
        """
        Check rate limit for this endpoint.

        Args:
            request: FastAPI request

        Raises:
            HTTPException: If rate limit exceeded
        """
        # Get client identifier
        user_id = getattr(request.state, "user_id", None)
        client_ip = request.client.host if request.client else "unknown"

        # Use IP for unauthenticated, user_id for authenticated
        client_key = f"user:{user_id}" if user_id else f"ip:{client_ip}"

        now = datetime.utcnow()
        timestamps = self.storage[client_key]

        # Remove old timestamps
        cutoff = now - timedelta(seconds=self.window_seconds)
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        # Check limit
        if len(timestamps) >= self.requests:
            oldest = timestamps[0]
            retry_after = int((oldest + timedelta(seconds=self.window_seconds) - now).total_seconds()) + 1

            logger.warning(
                f"Rate limit exceeded for {client_key} on {self.description}: "
                f"{len(timestamps)}/{self.requests} in {self.window_seconds}s"
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many {self.description} requests. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)}
            )

        # Record request
        timestamps.append(now)


# ============================================================================
# FACTORY FUNCTIONS FOR COMMON USE CASES
# ============================================================================

def login_rate_limit():
    """
    Rate limiter for login endpoint.

    Limit: 5 attempts per minute per IP.
    """
    return EndpointRateLimiter(
        requests=5,
        window_minutes=1,
        description="login"
    )


def password_reset_rate_limit():
    """
    Rate limiter for password reset endpoint.

    Limit: 3 attempts per 5 minutes per IP.
    """
    return EndpointRateLimiter(
        requests=3,
        window_minutes=5,
        description="password reset"
    )


def registration_rate_limit():
    """
    Rate limiter for registration endpoint.

    Limit: 3 registrations per hour per IP.
    """
    return EndpointRateLimiter(
        requests=3,
        window_minutes=60,
        description="registration"
    )


def email_verification_rate_limit():
    """
    Rate limiter for email verification resend.

    Limit: 5 attempts per 10 minutes per user.
    """
    return EndpointRateLimiter(
        requests=5,
        window_minutes=10,
        description="email verification"
    )


# ============================================================================
# AI ENDPOINT RATE LIMITERS (Tier-Based)
# ============================================================================

class AIEndpointRateLimiter:
    """
    Rate limiter for expensive AI operations with subscription tier awareness.

    Applies different rate limits based on user's subscription plan:
    - Free tier: 10 requests/hour
    - Pro tier: 50 requests/hour
    - Enterprise tier: 200 requests/hour
    """

    # Default limits per tier (requests per hour)
    TIER_LIMITS = {
        "free": 10,
        "pro": 50,
        "enterprise": 200,
        "default": 10  # For users without subscription
    }

    def __init__(
        self,
        custom_limits: Optional[dict] = None,
        description: str = "AI operation"
    ):
        """
        Initialize AI endpoint rate limiter.

        Args:
            custom_limits: Optional custom limits per tier (dict with tier names as keys)
            description: Description for error messages
        """
        self.limits = custom_limits or self.TIER_LIMITS
        self.description = description
        self.window_seconds = 3600  # 1 hour
        self.storage: Dict[str, deque] = defaultdict(deque)

    async def _get_user_tier(self, db: AsyncSession, user_id: str) -> str:
        """
        Get user's subscription tier.

        Args:
            db: Async database session
            user_id: User UUID

        Returns:
            Tier name (free, pro, enterprise, or default)
        """
        from src.api.models.subscription_models.subscriptions import (
            UserSubscription,
            SubscriptionStatus
        )
        from src.api.models.subscription_models.plans import SubscriptionPlan

        # Get active subscription
        stmt = select(UserSubscription).where(
            UserSubscription.user_id == user_id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        )
        result = await db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if not subscription:
            return "default"

        # Get plan
        stmt = select(SubscriptionPlan).where(
            SubscriptionPlan.id == subscription.plan_id
        )
        result = await db.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            return "default"

        # Map plan name to tier
        plan_name_lower = plan.name.lower()
        if plan_name_lower in self.limits:
            return plan_name_lower

        # Try to match common tier names
        if "free" in plan_name_lower:
            return "free"
        elif "pro" in plan_name_lower or "professional" in plan_name_lower:
            return "pro"
        elif "enterprise" in plan_name_lower or "business" in plan_name_lower:
            return "enterprise"

        return "default"

    async def __call__(
        self,
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(lambda: None)
    ):
        """
        Check AI operation rate limit based on user's subscription tier.

        Args:
            request: FastAPI request
            current_user: Authenticated user
            db: Async database session (will be injected by FastAPI)

        Raises:
            HTTPException: If rate limit exceeded
        """
        from src.api.database.async_database import get_async_db_context

        user_id = current_user.get("identity")

        # Get user's subscription tier (using async database session)
        async with get_async_db_context() as db:
            tier = await self._get_user_tier(db, user_id)
            max_requests = self.limits.get(tier, self.limits["default"])

        # Generate client key
        client_key = f"ai:{user_id}:{tier}"

        now = datetime.utcnow()
        timestamps = self.storage[client_key]

        # Remove old timestamps
        cutoff = now - timedelta(seconds=self.window_seconds)
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        # Check limit
        if len(timestamps) >= max_requests:
            oldest = timestamps[0]
            retry_after = int((oldest + timedelta(seconds=self.window_seconds) - now).total_seconds()) + 1

            logger.warning(
                f"AI rate limit exceeded for user {user_id} (tier: {tier}): "
                f"{len(timestamps)}/{max_requests} in {self.window_seconds}s"
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"AI {self.description} rate limit exceeded ({len(timestamps)}/{max_requests} per hour for {tier} tier). Try again in {retry_after} seconds. Upgrade your plan for higher limits.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                    "X-RateLimit-Tier": tier
                }
            )

        # Record request
        timestamps.append(now)

        logger.info(
            f"AI rate limit check passed for user {user_id} (tier: {tier}): "
            f"{len(timestamps)}/{max_requests} used"
        )


def ai_content_generation_rate_limit():
    """
    Rate limiter for AI content generation endpoint.

    Limits:
    - Free tier: 10 requests/hour
    - Pro tier: 50 requests/hour
    - Enterprise tier: 200 requests/hour
    """
    return AIEndpointRateLimiter(
        description="content generation"
    )


def ai_topic_generation_rate_limit():
    """
    Rate limiter for AI topic generation endpoint.

    Limits:
    - Free tier: 10 requests/hour
    - Pro tier: 50 requests/hour
    - Enterprise tier: 200 requests/hour
    """
    return AIEndpointRateLimiter(
        description="topic generation"
    )


def ai_knowledge_processing_rate_limit():
    """
    Rate limiter for AI knowledge base processing endpoint.

    Limits:
    - Free tier: 10 requests/hour
    - Pro tier: 50 requests/hour
    - Enterprise tier: 200 requests/hour
    """
    return AIEndpointRateLimiter(
        description="knowledge processing"
    )


# ============================================================================
# PAYMENT ENDPOINT RATE LIMITERS
# ============================================================================

def checkout_rate_limit():
    """
    Rate limiter for checkout endpoint.

    Limit: 5 checkout attempts per minute per user.
    Prevents rapid checkout session creation and potential abuse.
    """
    return EndpointRateLimiter(
        requests=5,
        window_minutes=1,
        description="checkout"
    )


def subscription_update_rate_limit():
    """
    Rate limiter for subscription update endpoints (upgrade/downgrade).

    Limit: 10 requests per minute per user.
    Prevents excessive plan changes.
    """
    return EndpointRateLimiter(
        requests=10,
        window_minutes=1,
        description="subscription update"
    )


def subscription_cancel_rate_limit():
    """
    Rate limiter for subscription cancellation endpoint.

    Limit: 3 cancellation attempts per minute per user.
    Prevents accidental rapid cancellations.
    """
    return EndpointRateLimiter(
        requests=3,
        window_minutes=1,
        description="subscription cancellation"
    )


def customer_portal_rate_limit():
    """
    Rate limiter for customer portal URL generation.

    Limit: 10 requests per minute per user.
    Prevents portal URL abuse.
    """
    return EndpointRateLimiter(
        requests=10,
        window_minutes=1,
        description="customer portal"
    )


# ============================================================================
# ADMIN ENDPOINT RATE LIMITERS (Phase 3, Task HIGH-4)
# ============================================================================

def role_management_rate_limit():
    """
    Rate limiter for role management endpoints (create/update/delete).

    Limit: 20 requests per minute per user.
    Prevents excessive role modifications and potential abuse.
    """
    return EndpointRateLimiter(
        requests=20,
        window_minutes=1,
        description="role management"
    )


def permission_management_rate_limit():
    """
    Rate limiter for permission management endpoints.

    Limit: 30 requests per minute per user.
    Allows for bulk permission updates while preventing abuse.
    """
    return EndpointRateLimiter(
        requests=30,
        window_minutes=1,
        description="permission management"
    )


def role_assignment_rate_limit():
    """
    Rate limiter for role assignment/revocation endpoints.

    Limit: 15 requests per minute per user.
    Prevents rapid role changes to users.
    """
    return EndpointRateLimiter(
        requests=15,
        window_minutes=1,
        description="role assignment"
    )
