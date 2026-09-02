"""
Request Tracking Middleware for Request ID Management

This middleware handles request ID generation, tracking, and correlation
across the entire request lifecycle. It ensures every request has a unique
identifier for logging, debugging, and error tracking.

Features:
- Automatic request ID generation
- Support for client-provided request IDs
- Request timing and performance tracking
- Integration with logging system
- Request correlation for debugging
"""

import time
from uuid import uuid4

from fastapi import Request, Response

from src.api.cache.redis_client import cache
from src.utils.logger import logger


class RequestTrackerMiddleware:
    """
    Middleware to track requests with unique IDs and performance metrics.
    Using pure ASGI interface to avoid BaseHTTPMiddleware issues with streaming responses.
    """

    def __init__(
        self,
        app,
        header_name: str = "X-Request-ID",
        generate_if_missing: bool = True,
        log_requests: bool = True,
        include_processing_time: bool = True,
    ):
        self.app = app
        self.header_name = header_name
        self.generate_if_missing = generate_if_missing
        self.log_requests = log_requests
        self.include_processing_time = include_processing_time
        self.sensitive_params = {"token", "secret", "password", "api_key", "key", "signature"}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request

        request = Request(scope, receive)

        # Generate or extract request ID
        request_id = self._get_or_generate_request_id(request)
        scope["state"] = scope.get("state", {})
        scope["state"]["request_id"] = request_id

        start_time = time.time()

        if self.log_requests:
            self._log_request_start(request, request_id)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message["status"]
                processing_time_ms = (
                    int((time.time() - start_time) * 1000) if self.include_processing_time else None
                )

                # Record metrics
                await self._record_api_metrics(processing_time_ms, status_code)

                # Add headers
                headers = list(message.get("headers", []))
                headers.append((self.header_name.encode(), request_id.encode()))
                if processing_time_ms is not None:
                    headers.append((b"X-Processing-Time-MS", str(processing_time_ms).encode()))
                headers.append((b"X-Response-Time", str(int(time.time())).encode()))
                message["headers"] = headers

                # Log success (only on start of response)
                if self.log_requests:
                    # We don't have the full response object here, so we simulate minimal logging
                    logger.info(
                        f"Request completed: {request.method} {request.url.path} - {status_code}",
                        extra={
                            "request_id": request_id,
                            "method": request.method,
                            "path": request.url.path,
                            "status_code": status_code,
                            "processing_time_ms": processing_time_ms,
                            "event_type": "request_success",
                        },
                    )

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            processing_time_ms = (
                int((time.time() - start_time) * 1000) if self.include_processing_time else None
            )
            await self._record_api_metrics(processing_time_ms, 500)
            if self.log_requests:
                self._log_request_error(request, exc, request_id, processing_time_ms)
            raise exc

    def _get_or_generate_request_id(self, request: Request) -> str:
        """
        Get request ID from headers or generate a new one.

        Args:
            request: Incoming request

        Returns:
            str: Request ID
        """
        # Try to get request ID from headers
        request_id = request.headers.get(self.header_name)

        # Validate existing request ID
        if request_id:
            # Basic validation - ensure it's not empty and reasonable length
            if len(request_id.strip()) < 3 or len(request_id) > 100:
                logger.warning(
                    f"Invalid request ID '{request_id}' in header {self.header_name}, generating new one"
                )
                request_id = None

        # Generate new request ID if needed
        if not request_id and self.generate_if_missing:
            request_id = self._generate_request_id()

        # Fallback if no generation enabled
        if not request_id:
            request_id = "unknown"

        return request_id

    def _generate_request_id(self) -> str:
        """
        Generate a unique request ID.

        Returns:
            str: Unique request ID
        """
        timestamp = int(time.time())
        uuid_part = str(uuid4()).replace("-", "")[:8]
        return f"req_{timestamp}_{uuid_part}"

    def _add_response_headers(
        self, response: Response, request_id: str, processing_time_ms: int = None
    ) -> None:
        """
        Add tracking headers to response.

        Args:
            response: Response to modify
            request_id: Request ID to include
            processing_time_ms: Processing time in milliseconds
        """
        # Always include request ID in response
        response.headers[self.header_name] = request_id

        # Include processing time if available
        if processing_time_ms is not None:
            response.headers["X-Processing-Time-MS"] = str(processing_time_ms)

        # Add server timestamp
        response.headers["X-Response-Time"] = str(int(time.time()))

    def _log_request_start(self, request: Request, request_id: str) -> None:
        """
        Log request start for debugging.

        Args:
            request: Incoming request
            request_id: Request ID
        """
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": self._get_redacted_query_params(request.query_params),
                "client_ip": self._get_client_ip(request),
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "event_type": "request_start",
            },
        )

    def _get_redacted_query_params(self, params) -> dict:
        """
        Get query parameters with sensitive values redacted.

        Args:
            params: Query parameters from request

        Returns:
            dict: Redacted parameters
        """
        redacted = dict(params)
        for key in redacted:
            if key.lower() in self.sensitive_params:
                redacted[key] = "[REDACTED]"
        return redacted

    def _log_request_success(
        self, request: Request, response: Response, request_id: str, processing_time_ms: int = None
    ) -> None:
        """
        Log successful request completion.

        Args:
            request: Original request
            response: Response object
            request_id: Request ID
            processing_time_ms: Processing time in milliseconds
        """
        extra_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "event_type": "request_success",
        }

        if processing_time_ms is not None:
            extra_data["processing_time_ms"] = processing_time_ms

        logger.info(
            f"Request completed: {request.method} {request.url.path} - {response.status_code}",
            extra=extra_data,
        )

    def _log_request_error(
        self,
        request: Request,
        exception: Exception,
        request_id: str,
        processing_time_ms: int = None,
    ) -> None:
        """
        Log request error.

        Args:
            request: Original request
            exception: Exception that occurred
            request_id: Request ID
            processing_time_ms: Processing time in milliseconds
        """
        extra_data = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "event_type": "request_error",
        }

        if processing_time_ms is not None:
            extra_data["processing_time_ms"] = processing_time_ms

        logger.error(
            f"Request failed: {request.method} {request.url.path} - {type(exception).__name__}",
            extra=extra_data,
            exc_info=True,
        )

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.

        Uses request.client.host which is set correctly by ProxyHeadersMiddleware.
        """
        return getattr(request.client, "host", "unknown") if request.client else "unknown"

    async def _record_api_metrics(self, processing_time_ms: int, status_code: int) -> None:
        """Record API metrics in Redis for monitoring dashboard."""
        try:
            redis = cache.redis
            if redis is None:
                return

            now_ts = int(time.time())
            minute_bucket = now_ts - (now_ts % 60)  # Round to minute

            pipe = redis.pipeline()
            # Increment request count for current minute
            count_key = f"metrics:api:count:{minute_bucket}"
            pipe.incr(count_key)
            pipe.expire(count_key, 3600)  # Keep 1 hour of minute buckets

            # Track response time (running sum for averaging)
            time_key = f"metrics:api:time_sum:{minute_bucket}"
            pipe.incrbyfloat(time_key, processing_time_ms)
            pipe.expire(time_key, 3600)

            # Track errors
            if status_code >= 500:
                error_key = f"metrics:api:errors:{minute_bucket}"
                pipe.incr(error_key)
                pipe.expire(error_key, 3600)

            await pipe.execute()
        except Exception:
            pass  # Non-critical, don't break request flow


def get_request_id(request: Request) -> str:
    """
    Helper function to get request ID from request state.

    Args:
        request: FastAPI request object

    Returns:
        str: Request ID or "unknown" if not available
    """
    return getattr(request.state, "request_id", "unknown")


def get_processing_time_ms(start_time: float) -> int:
    """
    Helper function to calculate processing time.

    Args:
        start_time: Start time from time.time()

    Returns:
        int: Processing time in milliseconds
    """
    return int((time.time() - start_time) * 1000)
