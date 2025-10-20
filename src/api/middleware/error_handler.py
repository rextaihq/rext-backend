"""
Centralized Error Handler Middleware for Consistent Error Responses

This module provides comprehensive error handling for FastAPI applications,
converting all exceptions into standardized error responses that match the
frontend expectations.

Features:
- Automatic exception to error response conversion
- Request ID correlation for error tracking
- Detailed error logging with context
- Security-conscious error message filtering
- Performance tracking for error scenarios
- Integration with monitoring systems
"""

import json
import traceback
from datetime import datetime
from typing import Callable, Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.schema.response_schemas import (
    ErrorResponse,
    ErrorCode,
    ErrorSeverity,
    create_error_response,
    get_error_code_for_http_status,
    get_severity_for_http_status,
)
from src.api.middleware.exceptions import WrextAPIException
from src.api.middleware.request_tracker import get_request_id, get_processing_time_ms
from src.utils.logger import logger

# Sentry integration (optional)
try:
    from src.api.lib.sentry_config import capture_exception_with_context
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Middleware for handling all exceptions and converting them to standardized responses.

    This middleware catches all exceptions that occur during request processing
    and converts them into consistent error responses. It also handles logging,
    request tracking, and security filtering of error details.
    """

    def __init__(
        self,
        app,
        include_debug_info: bool = False,
        log_full_traceback: bool = True,
        filter_sensitive_data: bool = True,
        max_error_details: int = 10
    ):
        """
        Initialize the error handler middleware.

        Args:
            app: FastAPI application instance
            include_debug_info: Include debug information in responses (dev only)
            log_full_traceback: Whether to log full tracebacks
            filter_sensitive_data: Whether to filter sensitive data from responses
            max_error_details: Maximum number of error details to include
        """
        super().__init__(app)
        self.include_debug_info = include_debug_info
        self.log_full_traceback = log_full_traceback
        self.filter_sensitive_data = filter_sensitive_data
        self.max_error_details = max_error_details

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        """
        Process request with comprehensive error handling.

        Args:
            request: Incoming request
            call_next: Next middleware/handler in chain

        Returns:
            JSONResponse: Either normal response or standardized error response
        """
        request_start_time = getattr(request.state, '_start_time', None)

        try:
            # Process the request normally
            response = await call_next(request)
            return response

        except Exception as exc:
            # Handle the exception and return standardized error response
            return await self._handle_exception(request, exc, request_start_time)

    async def _handle_exception(
        self,
        request: Request,
        exception: Exception,
        start_time: Optional[float] = None
    ) -> JSONResponse:
        """
        Convert exception to standardized error response.

        Args:
            request: Original request
            exception: Exception that occurred
            start_time: Request start time for performance tracking

        Returns:
            JSONResponse: Standardized error response
        """
        # Get request ID for correlation
        request_id = get_request_id(request)

        # Calculate processing time if available
        processing_time_ms = None
        if start_time:
            processing_time_ms = get_processing_time_ms(start_time)

        # Handle different exception types
        if isinstance(exception, WrextAPIException):
            error_response = self._handle_wrext_exception(
                exception, request_id, processing_time_ms
            )
        elif isinstance(exception, HTTPException):
            error_response = self._handle_http_exception(
                exception, request_id, processing_time_ms
            )
        elif isinstance(exception, ValidationError):
            error_response = self._handle_validation_exception(
                exception, request_id, processing_time_ms
            )
        else:
            error_response = self._handle_unexpected_exception(
                exception, request_id, processing_time_ms, request
            )

        # Log the error with appropriate detail level
        self._log_exception(request, exception, error_response, request_id)

        return JSONResponse(
            status_code=error_response.error["status_code"],
            content=json.loads(error_response.json())
        )

    def _handle_wrext_exception(
        self,
        exception: WrextAPIException,
        request_id: str,
        processing_time_ms: Optional[int] = None
    ) -> ErrorResponse:
        """
        Handle custom Wrext API exceptions.

        Args:
            exception: WrextAPIException instance
            request_id: Request ID for correlation
            processing_time_ms: Processing time in milliseconds

        Returns:
            ErrorResponse: Standardized error response
        """
        # Capture high/critical severity errors to Sentry
        if SENTRY_AVAILABLE and exception.severity in ["high", "critical"]:
            try:
                capture_exception_with_context(
                    exception,
                    context={
                        "request_id": request_id,
                        "error_code": exception.error_code.value,
                        "severity": exception.severity.value,
                        "details": exception.details,
                    },
                    level="error" if exception.severity == "high" else "fatal",
                    tags={
                        "error_code": exception.error_code.value,
                        "error_type": "wrext_api_exception",
                    }
                )
            except Exception as sentry_error:
                logger.warning(f"Failed to send error to Sentry: {sentry_error}")

        # Filter details if necessary
        details = exception.details
        if self.filter_sensitive_data:
            details = self._filter_sensitive_details(details)

        # Limit number of details
        if len(details) > self.max_error_details:
            details = details[:self.max_error_details]

        return create_error_response(
            code=exception.error_code,
            message=exception.message,
            status_code=exception.status_code,
            severity=exception.severity,
            details=[{"message": d.get("message", ""), "code": d.get("code", ""), "field": d.get("field")} for d in details] if details else None,
            request_id=request_id,
            processing_time_ms=processing_time_ms,
            context=self._filter_context(exception.context)
        )

    def _handle_http_exception(
        exception: HTTPException,
        request_id: str,
        processing_time_ms: Optional[int] = None
    ) -> ErrorResponse:
        """
        Handle FastAPI HTTP exceptions.

        Args:
            exception: HTTPException instance
            request_id: Request ID for correlation
            processing_time_ms: Processing time in milliseconds

        Returns:
            ErrorResponse: Standardized error response
        """
        error_code = get_error_code_for_http_status(exception.status_code)
        severity = get_severity_for_http_status(exception.status_code)

        # Extract additional details if present
        details = None
        if hasattr(exception, 'details') and exception.details:
            details = [{"message": str(exception.details), "code": "http_exception_detail"}]

        return create_error_response(
            code=error_code,
            message=str(exception.detail),
            status_code=exception.status_code,
            severity=severity,
            details=details,
            request_id=request_id,
            processing_time_ms=processing_time_ms
        )

    def _handle_validation_exception(
        self,
        exception: ValidationError,
        request_id: str,
        processing_time_ms: Optional[int] = None
    ) -> ErrorResponse:
        """
        Handle Pydantic validation exceptions.

        Args:
            exception: ValidationError instance
            request_id: Request ID for correlation
            processing_time_ms: Processing time in milliseconds

        Returns:
            ErrorResponse: Standardized error response
        """
        details = []
        for error in exception.errors():
            field_name = " -> ".join(str(loc) for loc in error.get("loc", []))
            details.append({
                "field": field_name,
                "message": error.get("msg", "Validation error"),
                "code": error.get("type", "validation_error"),
                "value": None  # Don't expose input values for security
            })

        # Limit number of validation errors
        if len(details) > self.max_error_details:
            details = details[:self.max_error_details]

        return create_error_response(
            code=ErrorCode.VALIDATION_FAILED,
            message=f"Validation failed with {len(exception.errors())} error(s)",
            status_code=422,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            request_id=request_id,
            processing_time_ms=processing_time_ms
        )

    def _handle_unexpected_exception(
        self,
        exception: Exception,
        request_id: str,
        processing_time_ms: Optional[int] = None,
        request: Optional[Request] = None
    ) -> ErrorResponse:
        """
        Handle unexpected exceptions that aren't explicitly handled.

        Args:
            exception: Exception instance
            request_id: Request ID for correlation
            processing_time_ms: Processing time in milliseconds
            request: Original request for context

        Returns:
            ErrorResponse: Standardized error response
        """
        # Capture to Sentry (unexpected errors are high priority)
        if SENTRY_AVAILABLE:
            try:
                context = {
                    "request_id": request_id,
                    "processing_time_ms": processing_time_ms,
                }

                if request:
                    context.update({
                        "request_path": request.url.path,
                        "request_method": request.method,
                        "request_query": str(request.url.query) if request.url.query else None,
                    })

                # Capture to Sentry with high severity
                capture_exception_with_context(
                    exception,
                    context=context,
                    level="error",
                    tags={
                        "error_handler": "unexpected",
                        "request_id": request_id,
                    }
                )
            except Exception as sentry_error:
                # Never let Sentry errors crash the app
                logger.warning(f"Failed to send error to Sentry: {sentry_error}")

        # Create safe error message
        if self.include_debug_info:
            message = f"Internal server error: {str(exception)}"
        else:
            message = "An internal server error occurred"

        # Prepare context for debugging (only if debug mode)
        context = {}
        if self.include_debug_info and request:
            context = {
                "exception_type": type(exception).__name__,
                "exception_message": str(exception),
                "request_path": request.url.path,
                "request_method": request.method,
            }

        return create_error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=message,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request_id=request_id,
            processing_time_ms=processing_time_ms,
            context=context if context else None
        )

    def _filter_sensitive_details(details: list) -> list:
        """
        Filter sensitive information from error details.

        Args:
            details: List of error detail dictionaries

        Returns:
            list: Filtered error details
        """
        if not details:
            return details

        filtered_details = []
        sensitive_fields = {
            'password', 'token', 'secret', 'key', 'authorization',
            'cookie', 'session', 'credential', 'private'
        }

        for detail in details:
            if isinstance(detail, dict):
                filtered_detail = detail.copy()

                # Remove sensitive field values
                field_name = detail.get('field', '').lower()
                if any(sensitive in field_name for sensitive in sensitive_fields):
                    filtered_detail['value'] = '[FILTERED]'

                # Truncate long values
                if 'value' in filtered_detail and isinstance(filtered_detail['value'], str):
                    if len(filtered_detail['value']) > 100:
                        filtered_detail['value'] = filtered_detail['value'][:97] + "..."

                filtered_details.append(filtered_detail)
            else:
                filtered_details.append(detail)

        return filtered_details

    def _filter_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter sensitive information from context data.

        Args:
            context: Context dictionary

        Returns:
            Dict[str, Any]: Filtered context
        """
        if not context or not self.filter_sensitive_data:
            return context

        filtered_context = {}
        sensitive_keys = {
            'password', 'token', 'secret', 'key', 'authorization',
            'cookie', 'session', 'credential', 'private', 'api_key'
        }

        for key, value in context.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                filtered_context[key] = '[FILTERED]'
            elif isinstance(value, str) and len(value) > 200:
                filtered_context[key] = value[:197] + "..."
            else:
                filtered_context[key] = value

        return filtered_context

    def _log_exception(
        self,
        request: Request,
        exception: Exception,
        error_response: ErrorResponse,
        request_id: str
    ) -> None:
        """
        Log exception with appropriate detail level.

        Args:
            request: Original request
            exception: Exception that occurred
            error_response: Generated error response
            request_id: Request ID for correlation
        """
        # Prepare logging context
        log_context = {
            "request_id": request_id,
            "error_code": error_response.error["code"],
            "status_code": error_response.error["status_code"],
            "severity": error_response.error["severity"],
            "method": request.method,
            "path": request.url.path,
            "exception_type": type(exception).__name__,
            "event_type": "exception_handled"
        }

        # Log based on severity
        error_severity = error_response.error["severity"]

        if error_severity in ["critical", "high"]:
            logger.error(
                f"Critical error in {request.method} {request.url.path}: {error_response.error['message']}",
                extra=log_context,
                exc_info=self.log_full_traceback
            )
        elif error_severity == "medium":
            logger.warning(
                f"Handled error in {request.method} {request.url.path}: {error_response.error['message']}",
                extra=log_context,
                exc_info=isinstance(exception, WrextAPIException) and self.log_full_traceback
            )
        else:  # low severity
            logger.info(
                f"Low severity error in {request.method} {request.url.path}: {error_response.error['message']}",
                extra=log_context
            )


def setup_exception_handlers(app: FastAPI) -> None:
    """
    Set up global exception handlers for the FastAPI application.

    Args:
        app: FastAPI application instance
    """
    @app.exception_handler(WrextAPIException)
    async def wrext_exception_handler(request: Request, exc: WrextAPIException):
        """Handle custom Wrext API exceptions."""
        request_id = get_request_id(request)

        error_response = create_error_response(
            code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            severity=exc.severity,
            details=[{"message": d.get("message", ""), "code": d.get("code", ""), "field": d.get("field")} for d in exc.details] if exc.details else None,
            request_id=request_id,
            context=exc.context
        )

        logger.error(
            f"Wrext API Exception: {exc.message}",
            extra={
                "request_id": request_id,
                "error_code": exc.error_code.value,
                "status_code": exc.status_code,
                "exception_type": type(exc).__name__
            }
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=json.loads(error_response.json())
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle FastAPI HTTP exceptions."""
        request_id = get_request_id(request)
        error_code = get_error_code_for_http_status(exc.status_code)
        severity = get_severity_for_http_status(exc.status_code)

        error_response = create_error_response(
            code=error_code,
            message=str(exc.detail),
            status_code=exc.status_code,
            severity=severity,
            request_id=request_id
        )

        logger.warning(
            f"HTTP Exception: {exc.status_code} - {exc.detail}",
            extra={
                "request_id": request_id,
                "status_code": exc.status_code,
                "error_code": error_code.value
            }
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=json.loads(error_response.json())
        )

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(request: Request, exc: ValidationError):
        """Handle Pydantic validation exceptions."""
        request_id = get_request_id(request)

        details = []
        for error in exc.errors():
            field_name = " -> ".join(str(loc) for loc in error.get("loc", []))
            details.append({
                "field": field_name,
                "message": error.get("msg", "Validation error"),
                "code": error.get("type", "validation_error")
            })

        error_response = create_error_response(
            code=ErrorCode.VALIDATION_FAILED,
            message=f"Request validation failed with {len(exc.errors())} error(s)",
            status_code=422,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            request_id=request_id
        )

        logger.warning(
            f"Validation Error: {len(exc.errors())} validation errors",
            extra={
                "request_id": request_id,
                "error_count": len(exc.errors()),
                "validation_errors": [{"field": " -> ".join(str(loc) for loc in e.get("loc", [])), "type": e.get("type")} for e in exc.errors()]
            }
        )

        return JSONResponse(
            status_code=422,
            content=json.loads(error_response.json())
        )