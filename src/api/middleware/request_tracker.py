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
from typing import Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.utils.logger import logger


class RequestTrackerMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track requests with unique IDs and performance metrics.

    This middleware:
    1. Generates or extracts request IDs from headers
    2. Adds request ID to request state for use in handlers
    3. Tracks request processing time
    4. Adds correlation headers to responses
    5. Logs request start/end for debugging
    """

    def __init__(
        self,
        app,
        header_name: str = "X-Request-ID",
        generate_if_missing: bool = True,
        log_requests: bool = True,
        include_processing_time: bool = True
    ):
        """
        Initialize the request tracker middleware.

        Args:
            app: FastAPI application instance
            header_name: Header name for request ID (default: X-Request-ID)
            generate_if_missing: Generate ID if not provided by client
            log_requests: Whether to log request start/end
            include_processing_time: Whether to track and include processing time
        """
        super().__init__(app)
        self.header_name = header_name
        self.generate_if_missing = generate_if_missing
        self.log_requests = log_requests
        self.include_processing_time = include_processing_time
        self.sensitive_params = {"token", "secret", "password", "api_key", "key", "signature"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with tracking and timing.

        Args:
            request: Incoming request
            call_next: Next middleware/handler in chain

        Returns:
            Response: Response with tracking headers added
        """
        # Generate or extract request ID
        request_id = self._get_or_generate_request_id(request)

        # Store request ID in request state for use in handlers
        request.state.request_id = request_id

        # Record start time for performance tracking
        start_time = time.time()

        # Log request start if enabled
        if self.log_requests:
            self._log_request_start(request, request_id)

        try:
            # Process request through the application
            response = await call_next(request)

            # Calculate processing time
            processing_time_ms = None
            if self.include_processing_time:
                processing_time_ms = int((time.time() - start_time) * 1000)

            # Add tracking headers to response
            self._add_response_headers(response, request_id, processing_time_ms)

            # Log successful request completion
            if self.log_requests:
                self._log_request_success(request, response, request_id, processing_time_ms)

            return response

        except Exception as exc:
            # Calculate processing time for errors too
            processing_time_ms = None
            if self.include_processing_time:
                processing_time_ms = int((time.time() - start_time) * 1000)

            # Log error (detailed error logging is handled by error handler)
            if self.log_requests:
                self._log_request_error(request, exc, request_id, processing_time_ms)

            # Re-raise the exception to be handled by error handler
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
        uuid_part = str(uuid4()).replace('-', '')[:8]
        return f"req_{timestamp}_{uuid_part}"

    def _add_response_headers(
        self,
        response: Response,
        request_id: str,
        processing_time_ms: int = None
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
                "event_type": "request_start"
            }
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
        self,
        request: Request,
        response: Response,
        request_id: str,
        processing_time_ms: int = None
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
            "event_type": "request_success"
        }

        if processing_time_ms is not None:
            extra_data["processing_time_ms"] = processing_time_ms

        logger.info(
            f"Request completed: {request.method} {request.url.path} - {response.status_code}",
            extra=extra_data
        )

    def _log_request_error(
        self,
        request: Request,
        exception: Exception,
        request_id: str,
        processing_time_ms: int = None
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
            "event_type": "request_error"
        }

        if processing_time_ms is not None:
            extra_data["processing_time_ms"] = processing_time_ms

        logger.error(
            f"Request failed: {request.method} {request.url.path} - {type(exception).__name__}",
            extra=extra_data,
            exc_info=True
        )

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.

        Uses request.client.host which is set correctly by ProxyHeadersMiddleware.
        """
        return getattr(request.client, "host", "unknown") if request.client else "unknown"


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