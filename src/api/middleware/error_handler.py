"""
Centralized Error Handler Middleware for Consistent Error Responses

This module provides comprehensive error handling for FastAPI applications,
converting all exceptions into standardized error responses that match the
frontend expectations.

Features:
- Automatic exception  to error response conversion
- Request ID correlation for error tracking
- Detailed error logging with context
- Security-conscious error message filtering
- Performance tracking for error scenarios
- Integration with monitoring systems
"""

import json
import traceback
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.api.lib.log_policy import get_severity_level, log_with_level
from src.api.middleware.exceptions import RextAPIException
from src.api.middleware.request_tracker import get_processing_time_ms, get_request_id
from src.api.schema.response_schemas import (
    ErrorCode,
    ErrorResponse,
    ErrorSeverity,
    create_error_response,
    get_error_code_for_http_status,
    get_severity_for_http_status,
)
from src.utils.logger import logger

# Sentry integration (optional)
try:
    from src.api.lib.sentry_config import capture_exception_with_context

    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


# Pydantic prefixes messages raised inside custom validators with these, which
# leaks straight into the UI as "Value error, URL must start with https://".
_PYDANTIC_MESSAGE_PREFIXES = ("Value error, ", "Assertion failed, ")
# Leading loc segments that say where the value came from, not which field.
_REQUEST_LOCATIONS = {"body", "query", "path", "header", "cookie"}
# Field-name words shown upper-case in labels ("avatar_url" -> "Avatar URL").
_ACRONYMS = {"url", "id", "api", "ssl", "seo"}
# How many field errors to spell out in the top-level message.
_MAX_SUMMARISED_ERRORS = 3


def _clean_validation_message(message: Any) -> str:
    """The validator's own message, without Pydantic's internal prefix."""
    text = str(message or "Invalid value")
    for prefix in _PYDANTIC_MESSAGE_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _validation_field_label(loc: Any) -> Optional[str]:
    """A human label for the field an error belongs to, e.g. "Full name".

    List indexes are skipped so an error on ``target_audience[2]`` still names
    the field. Model-level errors (loc is just ``("body",)``) have no field.
    """
    names = [
        str(part)
        for part in (loc or ())
        if not isinstance(part, int) and str(part) not in _REQUEST_LOCATIONS
    ]
    if not names:
        return None
    words = [
        word.upper() if word in _ACRONYMS else word for word in names[-1].lower().split("_") if word
    ]
    label = " ".join(words)
    return label[:1].upper() + label[1:]


def _summarise_validation_errors(errors: list) -> str:
    """One readable sentence for the response's top-level ``message``.

    The frontend shows ``error.message`` to the user, so this has to name the
    actual problem rather than "Request validation failed with 1 error(s)".
    """
    parts = []
    for error in errors[:_MAX_SUMMARISED_ERRORS]:
        message = _clean_validation_message(error.get("msg"))
        label = _validation_field_label(error.get("loc"))
        # "Workspace name cannot be empty" already names its field.
        if label and label.lower() not in message.lower():
            message = f"{label}: {message}"
        parts.append(message)
    if len(errors) > _MAX_SUMMARISED_ERRORS:
        parts.append(f"and {len(errors) - _MAX_SUMMARISED_ERRORS} more")
    return "; ".join(parts) or "Invalid request"


def _safe_extract_user_id(request: Request) -> Optional[str]:
    """
    Best-effort resolution of the authenticated user id for error-log
    attribution. Never raises.

    Most routes never populate ``request.state.user_id`` (only a handful of
    dependencies do), so fall back to decoding the bearer token the same way
    ``SentryUserContextMiddleware`` and ``get_current_user`` do.
    """
    try:
        state_user_id = getattr(request.state, "user_id", None)
        if state_user_id:
            return str(state_user_id)
    except Exception:
        pass

    try:
        auth_header = request.headers.get("Authorization", "") or ""
        if auth_header.startswith("Bearer "):
            from src.api.security.token_utils import decode_and_verify_token

            payload = decode_and_verify_token(auth_header[len("Bearer ") :]) or {}
            user_id = payload.get("id") or payload.get("sub")
            return str(user_id) if user_id else None
    except Exception:
        pass

    return None


async def _record_error(
    request: Request,
    *,
    severity: Optional[str],
    message: str,
    error_code: Optional[str],
    status_code: int,
    exception: Exception,
    request_id: str,
    stack_trace: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Write one handled error to ``error_logs`` so it surfaces in the admin
    System Monitoring dashboard. Best-effort: never raises, never affects the
    response being returned to the caller.

    Every exception handler routes through here. The persistence logic was
    previously copy-pasted into each handler, which is how they came to apply
    three different severity thresholds and how ``RequestValidationError`` was
    left with no persistence at all.
    """
    # Some handlers report a richer error themselves and then raise a friendlier
    # one for the response -- an integration that fails to connect records the
    # real vendor failure as critical, then answers the caller with "check your
    # Site URL and API Key". Without this the friendly exception would land as a
    # second, less useful row for the same event.
    if getattr(exception, "suppress_error_log", False):
        return

    try:
        from src.services.monitoring_service import MonitoringService

        path = request.url.path

        # The exception object and status code are both handed to the policy so
        # it can tell an unhandled crash from a vendor outage from a rejected
        # request. Classifying on the API severity string alone made all three
        # look identical on the dashboard.
        resolved = MonitoringService.resolve_error_log_severity(
            exception=exception,
            api_severity=severity,
            status_code=status_code,
            path=path,
        )
        if resolved is None:
            return

        await MonitoringService.persist_error_log(
            api_severity=severity,
            exception=exception,
            status_code=status_code,
            message=message,
            source=f"{request.method} {path}",
            path=path,
            user_id=_safe_extract_user_id(request),
            request_id=request_id,
            stack_trace=stack_trace,
            metadata={
                "error_code": error_code,
                "status_code": status_code,
                "exception_type": type(exception).__name__,
                **(extra_metadata or {}),
            },
        )
    except Exception as persist_error:  # noqa: BLE001 - never propagate
        logger.warning(f"Failed to persist error log: {persist_error}")


def _validation_error_metadata(exc: Exception) -> Dict[str, Any]:
    """
    Summarise which fields failed validation.

    A 422 is only actionable if you know what the client actually sent that was
    wrong, so record the offending field paths and rule names. Values are
    deliberately excluded -- a rejected request body routinely contains
    passwords and tokens.
    """
    try:
        errors = exc.errors()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - malformed/absent error list
        return {}

    from src.api.config import get_settings

    limit = get_settings().ERROR_LOG_MAX_VALIDATION_FIELDS

    return {
        "validation_error_count": len(errors),
        "invalid_fields": [
            {
                "field": " -> ".join(str(loc) for loc in err.get("loc", ())),
                "rule": err.get("type"),
                "message": err.get("msg"),
            }
            for err in errors[:limit]
        ],
    }


class ErrorHandlerMiddleware:
    """
    Middleware for handling all exceptions and converting them to standardized responses.
    Using pure ASGI interface to avoid BaseHTTPMiddleware issues with streaming responses.
    """

    def __init__(
        self,
        app,
        include_debug_info: bool = False,
        log_full_traceback: bool = True,
        filter_sensitive_data: bool = True,
        max_error_details: int = 10,
    ):
        self.app = app
        self.include_debug_info = include_debug_info
        self.log_full_traceback = log_full_traceback
        self.filter_sensitive_data = filter_sensitive_data
        self.max_error_details = max_error_details

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request

        request = Request(scope, receive)

        # Try to get start time from state (RequestTracker might have set it)
        request_start_time = None
        if hasattr(request.state, "_start_time"):
            request_start_time = request.state._start_time

        headers_sent = False

        async def send_wrapper(message):
            nonlocal headers_sent
            if message["type"] == "http.response.start":
                headers_sent = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if headers_sent:
                # If headers are already sent, we cannot send a new JSONResponse.
                # Log the error and let it propagate or let the connection close.
                logger.error(
                    f"Unhandled exception after headers sent: {type(exc).__name__}: {exc}",
                    exc_info=True,
                    extra={"request_id": get_request_id(request)},
                )
                raise exc

            # Handle the exception and return standardized error response
            response = await self._handle_exception(request, exc, request_start_time)

            # Send the response manually via ASGI
            await send(
                {
                    "type": "http.response.start",
                    "status": response.status_code,
                    "headers": list(response.headers.raw),
                }
            )
            await send({"type": "http.response.body", "body": response.body})

    async def _handle_exception(
        self, request: Request, exception: Exception, start_time: Optional[float] = None
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
        if isinstance(exception, RextAPIException):
            error_response = self._handle_rext_exception(exception, request_id, processing_time_ms)
        elif isinstance(exception, HTTPException):
            error_response = self._handle_http_exception(exception, request_id, processing_time_ms)
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

        # Persist the error to the admin monitoring dashboard (best-effort)
        await self._persist_error_log(
            request, exception, error_response, request_id, processing_time_ms
        )

        return JSONResponse(
            status_code=error_response.error["status_code"],
            content=json.loads(error_response.json()),
        )

    def _handle_rext_exception(
        self, exception: RextAPIException, request_id: str, processing_time_ms: Optional[int] = None
    ) -> ErrorResponse:
        """
        Handle custom Rext API exceptions.

        Args:
            exception: RextAPIException instance
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
                        "error_type": "rext_api_exception",
                    },
                )
            except Exception as sentry_error:
                logger.warning(f"Failed to send error to Sentry: {sentry_error}")

        # Filter details if necessary
        details = exception.details
        if self.filter_sensitive_data:
            details = self._filter_sensitive_details(details)

        # Limit number of details
        if len(details) > self.max_error_details:
            details = details[: self.max_error_details]

        return create_error_response(
            code=exception.error_code,
            message=exception.message,
            status_code=exception.status_code,
            severity=exception.severity,
            details=[
                {
                    "message": d.get("message", ""),
                    "code": d.get("code", ""),
                    "field": d.get("field"),
                }
                for d in details
            ]
            if details
            else None,
            request_id=request_id,
            processing_time_ms=processing_time_ms,
            context=self._filter_context(exception.context),
        )

    def _handle_http_exception(
        self, exception: HTTPException, request_id: str, processing_time_ms: Optional[int] = None
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
        if hasattr(exception, "details") and exception.details:
            details = [{"message": str(exception.details), "code": "http_exception_detail"}]

        return create_error_response(
            code=error_code,
            message=str(exception.detail),
            status_code=exception.status_code,
            severity=severity,
            details=details,
            request_id=request_id,
            processing_time_ms=processing_time_ms,
        )

    def _handle_validation_exception(
        self, exception: ValidationError, request_id: str, processing_time_ms: Optional[int] = None
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
            details.append(
                {
                    "field": field_name,
                    "message": _clean_validation_message(error.get("msg")),
                    "code": error.get("type", "validation_error"),
                    "value": None,  # Don't expose input values for security
                }
            )

        # Limit number of validation errors
        if len(details) > self.max_error_details:
            details = details[: self.max_error_details]

        return create_error_response(
            code=ErrorCode.VALIDATION_FAILED,
            message=_summarise_validation_errors(exception.errors()),
            status_code=422,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            request_id=request_id,
            processing_time_ms=processing_time_ms,
        )

    def _handle_unexpected_exception(
        self,
        exception: Exception,
        request_id: str,
        processing_time_ms: Optional[int] = None,
        request: Optional[Request] = None,
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
                    context.update(
                        {
                            "request_path": request.url.path,
                            "request_method": request.method,
                            "request_query": str(request.url.query) if request.url.query else None,
                        }
                    )

                # Capture to Sentry with high severity
                capture_exception_with_context(
                    exception,
                    context=context,
                    level="error",
                    tags={
                        "error_handler": "unexpected",
                        "request_id": request_id,
                    },
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
            context=context if context else None,
        )

    async def _persist_error_log(
        self,
        request: Request,
        exception: Exception,
        error_response: ErrorResponse,
        request_id: str,
        processing_time_ms: Optional[int] = None,
    ) -> None:
        """
        Write the handled error to the ``error_logs`` table so it surfaces in
        the admin System Monitoring dashboard. Best-effort and never raises.

        Only medium/high/critical severities are stored; low-severity noise
        (404s, most validation errors) and the monitoring endpoints themselves
        are skipped.
        """
        stack_trace = None
        if not isinstance(exception, (RextAPIException, HTTPException, ValidationError)):
            stack_trace = "".join(
                traceback.format_exception(type(exception), exception, exception.__traceback__)
            )

        await _record_error(
            request,
            severity=error_response.error.get("severity"),
            message=error_response.error.get("message") or str(exception),
            error_code=error_response.error.get("code"),
            status_code=error_response.error.get("status_code"),
            exception=exception,
            request_id=request_id,
            stack_trace=stack_trace,
            extra_metadata={"processing_time_ms": processing_time_ms},
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
            "password",
            "token",
            "secret",
            "key",
            "authorization",
            "cookie",
            "session",
            "credential",
            "private",
            "conflicting_value",
        }

        for detail in details:
            if isinstance(detail, dict):
                filtered_detail = detail.copy()

                # Remove sensitive field values
                field_name = detail.get("field", "").lower()
                if any(sensitive in field_name for sensitive in sensitive_fields):
                    filtered_detail["value"] = "[FILTERED]"

                # Truncate long values
                if "value" in filtered_detail and isinstance(filtered_detail["value"], str):
                    if len(filtered_detail["value"]) > 100:
                        filtered_detail["value"] = filtered_detail["value"][:97] + "..."

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
            "password",
            "token",
            "secret",
            "key",
            "authorization",
            "cookie",
            "session",
            "credential",
            "private",
            "api_key",
            "conflicting_value",
        }

        for key, value in context.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                filtered_context[key] = "[FILTERED]"
            elif isinstance(value, str) and len(value) > 200:
                filtered_context[key] = value[:197] + "..."
            else:
                filtered_context[key] = value

        return filtered_context

    def _log_exception(
        self, request: Request, exception: Exception, error_response: ErrorResponse, request_id: str
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
            "event_type": "exception_handled",
        }

        # Log based on severity
        error_severity = error_response.error["severity"]

        if error_severity in ["critical", "high"]:
            logger.error(
                f"Critical error in {request.method} {request.url.path}: {error_response.error['message']}",
                extra=log_context,
                exc_info=self.log_full_traceback,
            )
        elif error_severity == "medium":
            logger.warning(
                f"Handled error in {request.method} {request.url.path}: {error_response.error['message']}",
                extra=log_context,
                exc_info=isinstance(exception, RextAPIException) and self.log_full_traceback,
            )
        else:  # low severity
            logger.info(
                f"Low severity error in {request.method} {request.url.path}: {error_response.error['message']}",
                extra=log_context,
            )


def setup_exception_handlers(app: FastAPI) -> None:
    """
    Set up global exception handlers for the FastAPI application.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(RextAPIException)
    async def rext_exception_handler(request: Request, exc: RextAPIException):
        """Handle custom Rext API exceptions."""
        request_id = get_request_id(request)

        error_response = create_error_response(
            code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            severity=exc.severity,
            details=[
                {
                    "message": d.get("message", ""),
                    "code": d.get("code", ""),
                    "field": d.get("field"),
                }
                for d in exc.details
            ]
            if exc.details
            else None,
            request_id=request_id,
            context=exc.context,
        )

        log_level = get_severity_level(exc.severity.value)
        log_with_level(
            logger,
            log_level,
            f"Rext API Exception: {exc.message}",
            extra={
                "request_id": request_id,
                "error_code": exc.error_code.value,
                "status_code": exc.status_code,
                "severity": exc.severity.value,
                "exception_type": type(exc).__name__,
            },
        )

        # Persist serious errors to the monitoring dashboard (best-effort).
        # RextAPIException is handled here (not by the ASGI middleware), so
        # high/critical business errors would otherwise never be recorded.
        # Was gated on `severity_value in ("high", "critical")`. Nearly every
        # error this application raises is a RextAPIException at "medium", so
        # it was dropped here and error_logs stayed empty. The shared rule
        # inside _record_error decides now.
        #
        # exc.context is included because the user-facing message is
        # deliberately vague ("You do not have permission to perform this
        # action") so it cannot tell an attacker what to acquire. The Error
        # Logs tab is read by operators, not end users, and without the context
        # every authorisation failure looked identical -- the required
        # permission and workspace were raised and then discarded. Redacted
        # like every other stored field.
        await _record_error(
            request,
            severity=(exc.severity.value if hasattr(exc.severity, "value") else str(exc.severity)),
            message=exc.message,
            error_code=exc.error_code.value,
            status_code=exc.status_code,
            exception=exc,
            request_id=request_id,
            extra_metadata=dict(exc.context or {}),
        )

        return JSONResponse(status_code=exc.status_code, content=json.loads(error_response.json()))

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
            request_id=request_id,
        )

        logger.warning(
            f"HTTP Exception: {exc.status_code} - {exc.detail}",
            extra={
                "request_id": request_id,
                "status_code": exc.status_code,
                "error_code": error_code.value,
            },
        )

        # Persist HTTP errors to the monitoring dashboard (best-effort).
        # HTTPException is handled here rather than by the ASGI middleware, so
        # a route raising e.g. HTTPException(503) would otherwise never be
        # recorded.
        #
        # Was gated on `exc.status_code >= 500`, a third rule distinct from the
        # other two paths. Severity is already derived from the status code
        # above, so the shared rule covers it and the status check would only
        # reintroduce the divergence.
        await _record_error(
            request,
            severity=severity.value if hasattr(severity, "value") else str(severity),
            message=str(exc.detail),
            error_code=error_code.value,
            status_code=exc.status_code,
            exception=exc,
            request_id=request_id,
        )

        return JSONResponse(status_code=exc.status_code, content=json.loads(error_response.json()))

    async def validation_exception_handler(request: Request, exc: ValidationError):
        """
        Handle request/response validation failures.

        Registered for both ``RequestValidationError`` and ``ValidationError``.
        ``RequestValidationError`` is what FastAPI actually raises when a
        request body, query parameter or path parameter fails validation, and
        it was never registered here at all -- so every malformed request the
        frontend sent was answered with a 422 by FastAPI's built-in handler and
        recorded nowhere. That is the single most useful error class for
        diagnosing a frontend/backend contract mismatch, and it was invisible.
        """
        request_id = get_request_id(request)

        details = []
        for error in exc.errors():
            field_name = " -> ".join(str(loc) for loc in error.get("loc", []))
            details.append(
                {
                    "field": field_name,
                    "message": _clean_validation_message(error.get("msg")),
                    "code": error.get("type", "validation_error"),
                }
            )

        error_response = create_error_response(
            code=ErrorCode.VALIDATION_FAILED,
            message=_summarise_validation_errors(exc.errors()),
            status_code=422,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            request_id=request_id,
        )

        logger.warning(
            f"Validation Error: {len(exc.errors())} validation errors",
            extra={
                "request_id": request_id,
                "error_count": len(exc.errors()),
                "validation_errors": [
                    {
                        "field": " -> ".join(str(loc) for loc in e.get("loc", [])),
                        "type": e.get("type"),
                    }
                    for e in exc.errors()
                ],
            },
        )

        await _record_error(
            request,
            severity=ErrorSeverity.MEDIUM.value,
            message=f"Request validation failed with {len(exc.errors())} error(s)",
            error_code=ErrorCode.VALIDATION_FAILED.value,
            status_code=422,
            exception=exc,
            request_id=request_id,
            extra_metadata=_validation_error_metadata(exc),
        )

        return JSONResponse(status_code=422, content=json.loads(error_response.json()))

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
