"""
General API rate limiting middleware.

This module provides IP-based and user-based rate limiting to prevent API abuse.
Uses Redis sliding window (sorted sets) with in-memory fallback.

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

import hashlib
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.cache.redis_client import cache
from src.api.lib.log_policy import get_event_level, log_with_level
from src.api.security.dependencies import get_current_user
from src.utils.logger import logger

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR
REDIS_TTL_GRACE_SECONDS = SECONDS_PER_MINUTE
CLEANUP_TRIGGER_REQUEST_COUNT = 1000


@dataclass(frozen=True)
class EndpointLimitProfile:
    requests: int
    window_minutes: int
    description: str


LOGIN_LIMIT = EndpointLimitProfile(15, 1, "login")
PASSWORD_RESET_LIMIT = EndpointLimitProfile(10, 5, "password reset")
REGISTRATION_LIMIT = EndpointLimitProfile(10, 60, "registration")
OAUTH_LIMIT = EndpointLimitProfile(10, 5, "OAuth")
EMAIL_VERIFICATION_LIMIT = EndpointLimitProfile(5, 10, "email verification")
NOTIFICATION_READ_LIMIT = EndpointLimitProfile(60, 1, "notification read")
NOTIFICATION_WRITE_LIMIT = EndpointLimitProfile(20, 1, "notification write")
CHECKOUT_LIMIT = EndpointLimitProfile(5, 1, "checkout")
SUBSCRIPTION_UPDATE_LIMIT = EndpointLimitProfile(10, 1, "subscription update")
SUBSCRIPTION_CANCEL_LIMIT = EndpointLimitProfile(3, 1, "subscription cancellation")
CUSTOMER_PORTAL_LIMIT = EndpointLimitProfile(10, 1, "customer portal")
ROLE_MANAGEMENT_LIMIT = EndpointLimitProfile(20, 1, "role management")
PERMISSION_MANAGEMENT_LIMIT = EndpointLimitProfile(30, 1, "permission management")
ROLE_ASSIGNMENT_LIMIT = EndpointLimitProfile(15, 1, "role assignment")


class RateLimiter:
    """
    Sliding window rate limiter.

    Tracks requests in a time window and enforces limits.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        requests_per_day: int = 10000,
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
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

    async def check_rate_limit(self, client_key: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Check if request is within rate limits.

        Tries Redis sliding window first, falls back to in-memory.

        Args:
            client_key: Unique identifier for the client (IP or user ID)

        Returns:
            Tuple of (is_allowed, retry_after_seconds, limit_type)
        """
        # Try Redis first
        redis_result = await self._check_redis(client_key)
        if redis_result is not None:
            return redis_result

        # Fallback: in-memory sliding window
        now = datetime.now(timezone.utc)
        timestamps = self.requests[client_key]

        # Check minute limit
        self._cleanup_old_requests(timestamps, SECONDS_PER_MINUTE)
        if len(timestamps) >= self.requests_per_minute:
            oldest = timestamps[0]
            retry_after = (
                int((oldest + timedelta(seconds=SECONDS_PER_MINUTE) - now).total_seconds()) + 1
            )
            return False, retry_after, "minute"

        # Check hour limit
        self._cleanup_old_requests(timestamps, SECONDS_PER_HOUR)
        if len(timestamps) >= self.requests_per_hour:
            oldest = timestamps[0]
            retry_after = (
                int((oldest + timedelta(seconds=SECONDS_PER_HOUR) - now).total_seconds()) + 1
            )
            return False, retry_after, "hour"

        # Check day limit
        self._cleanup_old_requests(timestamps, SECONDS_PER_DAY)
        if len(timestamps) >= self.requests_per_day:
            oldest = timestamps[0]
            retry_after = (
                int((oldest + timedelta(seconds=SECONDS_PER_DAY) - now).total_seconds()) + 1
            )
            return False, retry_after, "day"

        # Record this request
        timestamps.append(now)

        return True, None, None

    async def _check_redis(
        self, client_key: str
    ) -> Optional[Tuple[bool, Optional[int], Optional[str]]]:
        """
        Redis sliding window rate limit using sorted sets.

        Returns None if Redis is unavailable (triggers in-memory fallback).
        """
        try:
            redis = cache.redis
            if redis is None:
                return None

            now_ts = time.time()
            key = f"ratelimit:{client_key}"

            # Clean old entries + count per window in one pipeline
            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, now_ts - SECONDS_PER_DAY)
            pipe.zcount(key, now_ts - SECONDS_PER_MINUTE, "+inf")
            pipe.zcount(key, now_ts - SECONDS_PER_HOUR, "+inf")
            pipe.zcount(key, now_ts - SECONDS_PER_DAY, "+inf")
            results = await pipe.execute()

            minute_count = results[1]
            hour_count = results[2]
            day_count = results[3]

            limits = [
                (minute_count, self.requests_per_minute, SECONDS_PER_MINUTE, "minute"),
                (hour_count, self.requests_per_hour, SECONDS_PER_HOUR, "hour"),
                (day_count, self.requests_per_day, SECONDS_PER_DAY, "day"),
            ]

            for count, limit, window, label in limits:
                if count >= limit:
                    return False, window, label

            # Allowed — record request
            pipe2 = redis.pipeline()
            pipe2.zadd(key, {str(now_ts): now_ts})
            pipe2.expire(key, SECONDS_PER_DAY + SECONDS_PER_MINUTE)
            await pipe2.execute()

            return True, None, None

        except Exception as e:
            logger.debug(f"Redis rate limit unavailable, using in-memory: {e}")
            return None

    def get_client_key(self, request: Request) -> str:
        """
        Generate a unique key for the client.

        Prefers user ID if authenticated, falls back to IP address.
        Uses request.client.host (set by ProxyHeadersMiddleware for proxied requests).
        """
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"

        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def cleanup_old_entries(self) -> int:
        """
        Clean up stale entries to prevent memory growth.

        Removes entries with no requests in the last 24 hours.

        Returns:
            Number of entries removed
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=SECONDS_PER_DAY)
        keys_to_remove = []

        for key, timestamps in self.requests.items():
            if not timestamps or timestamps[-1] < cutoff:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.requests[key]

        if keys_to_remove:
            logger.info(f"Rate limiter cleanup: removed {len(keys_to_remove)} stale entries")

        return len(keys_to_remove)


class RateLimiterMiddleware:
    """
    FastAPI middleware for rate limiting requests.
    Using pure ASGI interface to avoid BaseHTTPMiddleware issues with streaming responses.
    """

    # Paths exempt from rate limiting
    EXEMPT_PATHS = {
        "/",
        "/health",
        "/health/live",
        "/health/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/status",
        "/ok",
        "/info",
    }

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        requests_per_day: int = 10000,
        enable: bool = True,
    ):
        self.app = app
        self.limiter = RateLimiter(
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
            requests_per_day=requests_per_day,
        )
        self.enable = enable
        self.cleanup_counter = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.enable:
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request

        request = Request(scope, receive)

        # Skip exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # Get client identifier
        client_key = self.limiter.get_client_key(request)

        # Check rate limit
        is_allowed, retry_after, limit_type = await self.limiter.check_rate_limit(client_key)

        if not is_allowed:
            log_with_level(
                logger,
                get_event_level("rate_limit_exceeded"),
                f"Rate limit exceeded for {client_key}: {limit_type} limit reached. Retry after {retry_after}s",
            )

            # Standard 429 response
            headers = [
                (b"content-type", b"application/json"),
                (
                    b"x-ratelimit-limit",
                    str(getattr(self.limiter, f"requests_per_{limit_type}")).encode(),
                ),
                (b"x-ratelimit-remaining", b"0"),
                (b"x-ratelimit-reset", str(retry_after).encode()),
                (b"retry-after", str(retry_after).encode()),
            ]

            payload = {
                "error": {
                    "message": f"Rate limit exceeded. Too many requests per {limit_type}. Try again in {retry_after} seconds.",
                    "code": "rate_limit_exceeded",
                    "status_code": 429,
                }
            }

            await send({"type": "http.response.start", "status": 429, "headers": headers})
            await send({"type": "http.response.body", "body": json.dumps(payload).encode()})
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Add headers to successful responses
                headers = list(message.get("headers", []))

                # We can't easily calculate 'remaining' here without re-checking,
                # but we can at least add the limit header if it's not a streaming response issues.
                # For simplicity, we just pass through.

                message["headers"] = headers
            await send(message)

        # Periodic cleanup
        self.cleanup_counter += 1
        if self.cleanup_counter >= CLEANUP_TRIGGER_REQUEST_COUNT:
            self.limiter.cleanup_old_entries()
            self.cleanup_counter = 0

        await self.app(scope, receive, send_wrapper)


# ============================================================================
# ENDPOINT-SPECIFIC RATE LIMITERS (Dependency Injection)
# ============================================================================


class EndpointRateLimiter:
    """
    Rate limiter for specific endpoints (via dependency injection).

    More strict limits for sensitive endpoints like login, password reset, etc.
    """

    def __init__(self, requests: int = 50, window_minutes: int = 1, description: str = "endpoint"):
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

        Tries Redis first, falls back to in-memory.

        Args:
            request: FastAPI request

        Raises:
            HTTPException: If rate limit exceeded
        """
        # Get client identifier
        user_id = getattr(request.state, "user_id", None)
        client_ip = request.client.host if request.client else "unknown"

        # Base key is IP-based
        client_key = f"ip:{client_ip}"

        # If authenticated, use user identity
        if user_id:
            client_key = f"user:{user_id}"
        # For unauthenticated sensitive requests, try to include email in the key
        # to prevent one user's failed attempts from blocking everyone on the same IP.
        elif request.method == "POST":
            try:
                # Fast check to see if it's likely a JSON auth request
                content_type = request.headers.get("content-type", "").lower()
                path = request.url.path.lower()

                if "application/json" in content_type and any(
                    p in path for p in ["login", "register", "verify", "password"]
                ):
                    # FastAPI caches the body, so this is safe and won't consume the stream
                    body = await request.json()
                    email = body.get("email") or body.get("email_address")
                    if email:
                        # Use a truncated hash to keep keys manageable and protect privacy
                        email_h = hashlib.sha256(email.lower().strip().encode()).hexdigest()[:12]
                        client_key = f"email:{email_h}:ip:{client_ip}"
            except Exception:
                # Fallback to IP-only if body parsing fails
                pass

        # Try Redis sliding window
        redis_checked = False
        try:
            redis = cache.redis
            if redis is not None:
                now_ts = time.time()
                key = f"ratelimit:{self.description}:{client_key}"

                pipe = redis.pipeline()
                pipe.zremrangebyscore(key, 0, now_ts - self.window_seconds)
                pipe.zcount(key, now_ts - self.window_seconds, "+inf")
                results = await pipe.execute()
                count = results[1]

                if count >= self.requests:
                    log_with_level(
                        logger,
                        get_event_level("rate_limit_exceeded"),
                        f"Rate limit exceeded for {client_key} on {self.description}: "
                        f"{count}/{self.requests} in {self.window_seconds}s",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Too many {self.description} requests. Try again later.",
                        headers={"Retry-After": str(self.window_seconds)},
                    )

                pipe2 = redis.pipeline()
                pipe2.zadd(key, {str(now_ts): now_ts})
                pipe2.expire(key, self.window_seconds + 60)
                await pipe2.execute()
                redis_checked = True
        except HTTPException:
            raise
        except Exception:
            pass  # Fall through to in-memory

        if redis_checked:
            return

        # Fallback: in-memory
        now = datetime.now(timezone.utc)
        timestamps = self.storage[client_key]

        cutoff = now - timedelta(seconds=self.window_seconds)
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) >= self.requests:
            oldest = timestamps[0]
            retry_after = (
                int((oldest + timedelta(seconds=self.window_seconds) - now).total_seconds()) + 1
            )

            log_with_level(
                logger,
                get_event_level("rate_limit_exceeded"),
                f"Rate limit exceeded for {client_key} on {self.description}: "
                f"{len(timestamps)}/{self.requests} in {self.window_seconds}s",
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many {self.description} requests. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)


def get_device_fingerprint(request: Request) -> str:
    """
    Derive a coarse "device" identifier from IP + User-Agent.

    Not a persistent device ID (none exists in this codebase) - just a fingerprint
    used to correlate requests likely coming from the same browser/machine.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    raw = f"{client_ip}|{user_agent}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def notification_read_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for notification read endpoints (GET).

    Limit: 60 requests per minute per user.
    Generous enough for normal polling but prevents abuse.
    """
    return _build_endpoint_limiter(NOTIFICATION_READ_LIMIT)


def notification_write_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for notification write endpoints (POST mark-as-read, clear).

    Limit: 20 requests per minute per user.
    Stricter because write operations are more expensive.
    """
    return _build_endpoint_limiter(NOTIFICATION_WRITE_LIMIT)


REGISTRATION_REQUESTS_PER_HOUR = 3
REGISTRATION_WINDOW_MINUTES = 60


def email_verification_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for email verification attempts.

    Limit: 5 attempts per 10 minutes per user.
    """
    return _build_endpoint_limiter(EMAIL_VERIFICATION_LIMIT)


def _build_endpoint_limiter(profile: EndpointLimitProfile) -> EndpointRateLimiter:
    return EndpointRateLimiter(
        requests=profile.requests,
        window_minutes=profile.window_minutes,
        description=profile.description,
    )


def login_rate_limit() -> EndpointRateLimiter:
    return _build_endpoint_limiter(LOGIN_LIMIT)


def media_upload_rate_limit():
    """
    Rate limiter for media upload endpoint.

    Limit: 10 uploads per minute per user.
    Prevents storage abuse and server resource exhaustion.
    """
    return EndpointRateLimiter(requests=10, window_minutes=1, description="media upload")


def password_reset_rate_limit() -> EndpointRateLimiter:
    return _build_endpoint_limiter(PASSWORD_RESET_LIMIT)


def registration_rate_limit() -> EndpointRateLimiter:
    return _build_endpoint_limiter(REGISTRATION_LIMIT)


def oauth_rate_limit() -> EndpointRateLimiter:
    return _build_endpoint_limiter(OAUTH_LIMIT)


def invitation_creation_rate_limit():
    """
    Rate limiter for invitation creation endpoints.

    Limit: 10 invitations per 5 minutes per user.
    Prevents email spam and quota exhaustion while allowing
    reasonable batch invitation workflows.
    """
    return EndpointRateLimiter(requests=10, window_minutes=5, description="invitation creation")


def admin_invitation_rate_limit():
    """
    Rate limiter for admin invitation creation endpoints.

    Limit: 5 admin invitations per 5 minutes per user.
    More restrictive than workspace invitations because admin
    invitations grant platform-level privileges.
    """
    return EndpointRateLimiter(
        requests=5, window_minutes=5, description="admin invitation creation"
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
        "default": 10,  # For users without subscription
    }

    def __init__(self, custom_limits: Optional[dict] = None, description: str = "AI operation"):
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
        from sqlalchemy import case

        from src.api.models.subscription_models.plans import SubscriptionPlan
        from src.api.models.subscription_models.subscriptions import (
            SubscriptionStatus,
            UserSubscription,
        )

        # Get active subscription (prioritize ACTIVE over TRIAL, then most recent)
        priority = case((UserSubscription.status == SubscriptionStatus.ACTIVE, 1), else_=0)
        stmt = (
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            )
            .order_by(priority.desc(), UserSubscription.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if not subscription:
            return "default"

        # Get plan
        stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
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
        db: AsyncSession = Depends(lambda: None),
    ):
        """
        Check AI operation rate limit based on user's subscription tier.

        Tries Redis first, falls back to in-memory.

        Args:
            request: FastAPI request
            current_user: Authenticated user
            db: Async database session (will be injected by FastAPI)

        Raises:
            HTTPException: If rate limit exceeded
        """
        from src.api.database.async_database import get_async_db_context

        user_id = current_user.get("identity")

        # Get user's subscription tier
        async with get_async_db_context() as db:
            tier = await self._get_user_tier(db, user_id)
            max_requests = self.limits.get(tier, self.limits["default"])

        client_key = f"ai:{user_id}:{tier}"

        # Try Redis sliding window
        redis_checked = False
        try:
            redis = cache.redis
            if redis is not None:
                now_ts = time.time()
                key = f"ratelimit:ai:{self.description}:{client_key}"

                pipe = redis.pipeline()
                pipe.zremrangebyscore(key, 0, now_ts - self.window_seconds)
                pipe.zcount(key, now_ts - self.window_seconds, "+inf")
                results = await pipe.execute()
                count = results[1]

                if count >= max_requests:
                    log_with_level(
                        logger,
                        get_event_level("rate_limit_exceeded"),
                        f"AI rate limit exceeded for user {user_id} (tier: {tier}): "
                        f"{count}/{max_requests} in {self.window_seconds}s",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"AI {self.description} rate limit exceeded ({count}/{max_requests} per hour for {tier} tier). Upgrade your plan for higher limits.",
                        headers={
                            "Retry-After": str(self.window_seconds),
                            "X-RateLimit-Limit": str(max_requests),
                            "X-RateLimit-Remaining": "0",
                            "X-RateLimit-Tier": tier,
                        },
                    )

                pipe2 = redis.pipeline()
                pipe2.zadd(key, {str(now_ts): now_ts})
                pipe2.expire(key, self.window_seconds + 60)
                await pipe2.execute()
                redis_checked = True
        except HTTPException:
            raise
        except Exception:
            pass  # Fall through to in-memory

        if redis_checked:
            return

        # Fallback: in-memory
        now = datetime.now(timezone.utc)
        timestamps = self.storage[client_key]

        cutoff = now - timedelta(seconds=self.window_seconds)
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) >= max_requests:
            oldest = timestamps[0]
            retry_after = (
                int((oldest + timedelta(seconds=self.window_seconds) - now).total_seconds()) + 1
            )

            log_with_level(
                logger,
                get_event_level("rate_limit_exceeded"),
                f"AI rate limit exceeded for user {user_id} (tier: {tier}): "
                f"{len(timestamps)}/{max_requests} in {self.window_seconds}s",
            )

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"AI {self.description} rate limit exceeded ({len(timestamps)}/{max_requests} per hour for {tier} tier). Upgrade your plan for higher limits.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Tier": tier,
                },
            )

        timestamps.append(now)


def ai_content_generation_rate_limit():
    """
    Rate limiter for AI content generation endpoint.

    Limits:
    - Free tier: 10 requests/hour
    - Pro tier: 50 requests/hour
    - Enterprise tier: 200 requests/hour
    """
    return AIEndpointRateLimiter(description="content generation")


def ai_knowledge_processing_rate_limit():
    """
    Rate limiter for AI knowledge base processing endpoint.

    Limits:
    - Free tier: 10 requests/hour
    - Pro tier: 50 requests/hour
    - Enterprise tier: 200 requests/hour
    """
    return AIEndpointRateLimiter(description="knowledge processing")


# ============================================================================
# PAYMENT ENDPOINT RATE LIMITERS
# ============================================================================


def checkout_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for checkout endpoint.

    Limit: 5 checkout attempts per minute per user.
    Prevents rapid checkout session creation and potential abuse.
    """
    return _build_endpoint_limiter(CHECKOUT_LIMIT)


def subscription_update_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for subscription update endpoints (upgrade/downgrade).

    Limit: 10 requests per minute per user.
    Prevents excessive plan changes.
    """
    return _build_endpoint_limiter(SUBSCRIPTION_UPDATE_LIMIT)


def subscription_cancel_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for subscription cancellation endpoint.

    Limit: 3 cancellation attempts per minute per user.
    Prevents accidental rapid cancellations.
    """
    return _build_endpoint_limiter(SUBSCRIPTION_CANCEL_LIMIT)


def customer_portal_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for customer portal URL generation.

    Limit: 10 requests per minute per user.
    Prevents portal URL abuse.
    """
    return _build_endpoint_limiter(CUSTOMER_PORTAL_LIMIT)


# ============================================================================
# ADMIN ENDPOINT RATE LIMITERS (Phase 3, Task HIGH-4)
# ============================================================================


def role_management_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for role management endpoints (create/update/delete).

    Limit: 20 requests per minute per user.
    Prevents excessive role modifications and potential abuse.
    """
    return _build_endpoint_limiter(ROLE_MANAGEMENT_LIMIT)


def permission_management_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for permission management endpoints.

    Limit: 30 requests per minute per user.
    Allows for bulk permission updates while preventing abuse.
    """
    return _build_endpoint_limiter(PERMISSION_MANAGEMENT_LIMIT)


def role_assignment_rate_limit() -> EndpointRateLimiter:
    """
    Rate limiter for role assignment/revocation endpoints.

    Limit: 15 requests per minute per user.
    Prevents rapid role changes to users.
    """
    return _build_endpoint_limiter(ROLE_ASSIGNMENT_LIMIT)


def audit_export_rate_limit():
    """
    Rate limiter for audit log export endpoint.

    Limit: 5 export requests per 5 minutes per user.
    Prevents rapid bulk data exfiltration and resource exhaustion.
    """
    return EndpointRateLimiter(requests=5, window_minutes=5, description="audit export")
