"""
Custom Exception Classes for Consistent Error Handling

This module defines custom exception classes that map to specific error scenarios
in the application. These exceptions are automatically caught by the error handler
middleware and converted to standardized error responses.

Usage:
    from src.api.middleware.exceptions import ResourceNotFoundException

    # In route handlers
    if not user:
        raise ResourceNotFoundException(
            message="User not found",
            resource_type="user",
            resource_id=user_id
        )
"""

from typing import Any, Dict, List, Optional

from src.api.schema.response_schemas import ErrorCode, ErrorSeverity


class RextAPIException(Exception):
    """
    Base exception class for all API-related errors.

    All custom exceptions should inherit from this class to ensure
    consistent error handling and response formatting.
    """

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        status_code: int = 500,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.severity = severity
        self.details = details or []
        self.context = context or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for response formatting."""
        return {
            "code": self.error_code.value,
            "message": self.message,
            "severity": self.severity.value,
            "status_code": self.status_code,
            "details": self.details,
            "context": self.context,
        }


# ============================================================================
# VALIDATION EXCEPTIONS (4xx)
# ============================================================================


class RextValidationException(RextAPIException):
    """Exception for validation errors."""

    def __init__(
        self,
        message: str = "Validation failed",
        field_errors: Optional[Dict[str, List[str]]] = None,
        **kwargs,
    ):
        details = []
        if field_errors:
            for field, errors in field_errors.items():
                for error in errors:
                    details.append(
                        {"field": field, "message": error, "code": "field_validation_error"}
                    )

        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_FAILED,
            status_code=422,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            **kwargs,
        )


class InvalidFormatException(RextValidationException):
    """Exception for invalid data format errors."""

    def __init__(self, field_name: str, expected_format: str, received_value: Any = None):
        message = f"Invalid format for field '{field_name}'. Expected: {expected_format}"
        field_errors = {field_name: [message]}

        super().__init__(
            message=message,
            field_errors=field_errors,
            context={
                "field": field_name,
                "expected_format": expected_format,
                "received_value": str(received_value) if received_value else None,
            },
        )


# ============================================================================
# AUTHENTICATION & AUTHORIZATION EXCEPTIONS (401/403)
# ============================================================================


class RextAuthenticationException(RextAPIException):
    """Exception for authentication errors."""

    def __init__(self, message: str = "Authentication failed", **kwargs):
        # Allow overriding error_code from subclasses (like TokenExpiredException)
        error_code = kwargs.pop("error_code", ErrorCode.UNAUTHORIZED)

        super().__init__(
            message=message,
            error_code=error_code,
            status_code=401,
            severity=ErrorSeverity.MEDIUM,
            **kwargs,
        )


class RextAuthorizationException(RextAPIException):
    """Exception for authorization errors."""

    def __init__(self, message: str = "Access forbidden", resource: str = None, **kwargs):
        # Extract and remove parameters that shouldn't be passed to parent
        required_permission = kwargs.pop("required_permission", None)
        context = kwargs.pop("context", {})

        if resource:
            context["resource"] = resource
        if required_permission:
            context["required_permission"] = required_permission

        # Allow overriding error_code from subclasses (like WorkspaceAccessDeniedException)
        error_code = kwargs.pop("error_code", ErrorCode.FORBIDDEN)

        super().__init__(
            message=message,
            error_code=error_code,
            status_code=403,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs,
        )


class TokenExpiredException(RextAuthenticationException):
    """Exception for expired authentication tokens."""

    def __init__(self, message: str = "Authentication token has expired"):
        super().__init__(
            message=message,
            error_code=ErrorCode.TOKEN_EXPIRED,
            context={"suggestion": "Please refresh your token or log in again"},
        )


class InvalidAPIKeyException(RextAuthenticationException):
    """Exception for invalid API key errors."""

    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(
            message=message, context={"suggestion": "Please check your API key configuration"}
        )


# ============================================================================
# BUSINESS LOGIC EXCEPTIONS (400/404/409)
# ============================================================================


class RextBusinessException(RextAPIException):
    """Base class for business logic related exceptions."""

    pass


class ResourceNotFoundException(RextBusinessException):
    """Exception for when a requested resource is not found."""

    def __init__(
        self,
        message: str = None,
        resource_type: str = "resource",
        resource_id: str = None,
        **kwargs,
    ):
        if not message:
            if resource_id:
                message = f"{resource_type.title()} with ID '{resource_id}' not found"
            else:
                message = f"{resource_type.title()} not found"

        context = kwargs.pop("context", {})  # Use pop to remove from kwargs
        context.update({"resource_type": resource_type, "resource_id": resource_id})

        super().__init__(
            message=message,
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.LOW,
            context=context,
            **kwargs,
        )


class DuplicateResourceException(RextBusinessException):
    """Exception for when trying to create a resource that already exists."""

    def __init__(
        self,
        message: str = None,
        resource_type: str = "resource",
        conflicting_field: str = None,
        conflicting_value: str = None,
        **kwargs,
    ):
        if not message:
            if conflicting_field and conflicting_value:
                message = f"{resource_type.title()} with {conflicting_field} '{conflicting_value}' already exists"
            else:
                message = f"{resource_type.title()} already exists"

        context = kwargs.pop("context", {})
        context.update(
            {
                "resource_type": resource_type,
                "conflicting_field": conflicting_field,
                "conflicting_value": conflicting_value,
            }
        )

        super().__init__(
            message=message,
            error_code=ErrorCode.DUPLICATE_RESOURCE,
            status_code=409,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs,
        )


class BusinessRuleViolationException(RextBusinessException):
    """Exception for business rule violations."""

    def __init__(self, message: str, rule_name: str = None, **kwargs):
        context = kwargs.get("context", {})
        if rule_name:
            context["rule_name"] = rule_name

        super().__init__(
            message=message,
            error_code=ErrorCode.BUSINESS_RULE_VIOLATION,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs,
        )


class QuotaExceededException(RextBusinessException):
    """Exception for quota/limit exceeded errors."""

    def __init__(
        self,
        message: str = "Quota exceeded",
        quota_type: str = None,
        current_value: int = None,
        limit_value: int = None,
        **kwargs,
    ):
        context = kwargs.get("context", {})
        context.update(
            {"quota_type": quota_type, "current_value": current_value, "limit_value": limit_value}
        )

        super().__init__(
            message=message,
            error_code=ErrorCode.QUOTA_EXCEEDED,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs,
        )


class RateLimitExceededException(RextBusinessException):
    """Exception for rate limit exceeded errors."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = None, **kwargs):
        context = kwargs.get("context", {})
        if retry_after:
            context["retry_after_seconds"] = retry_after
            message += f". Try again in {retry_after} seconds"

        super().__init__(
            message=message,
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=429,
            # Raised to MEDIUM so it reaches error_logs. At LOW it was below
            # the lowest storable level, so a client hammering the API -- the
            # signature of a runaway retry loop or a scripted attack -- left no
            # trace in the admin Error Logs tab. It is the one business
            # exception an operator needs to see a burst of, and volume is
            # exactly what makes it meaningful.
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs,
        )


# ============================================================================
# EXTERNAL SERVICE EXCEPTIONS (502/503)
# ============================================================================


class RextExternalServiceException(RextAPIException):
    """Exception for external service related errors."""

    def __init__(self, message: str, service_name: str = None, service_error: str = None, **kwargs):
        context = kwargs.pop("context", {})
        context.update({"service_name": service_name, "service_error": service_error})

        # Allow overriding from subclasses (like DatabaseConnectionException).
        # status_code and severity must be popped for the same reason as
        # error_code: DatabaseConnectionException passes status_code=503, and
        # leaving it in kwargs made it collide with the literal below, so
        # constructing one raised TypeError instead of the intended exception.
        error_code = kwargs.pop("error_code", ErrorCode.EXTERNAL_SERVICE_ERROR)
        status_code = kwargs.pop("status_code", 502)
        severity = kwargs.pop("severity", ErrorSeverity.HIGH)

        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            severity=severity,
            context=context,
            **kwargs,
        )


class ExternalServiceTimeoutException(RextExternalServiceException):
    """Exception for external service timeout errors."""

    def __init__(self, service_name: str, timeout_seconds: int = None, **kwargs):
        message = f"Timeout communicating with {service_name}"
        if timeout_seconds:
            message += f" after {timeout_seconds} seconds"

        context = kwargs.get("context", {})
        context.update({"timeout_seconds": timeout_seconds})

        super().__init__(
            message=message,
            service_name=service_name,
            error_code=ErrorCode.EXTERNAL_SERVICE_TIMEOUT,
            status_code=504,
            context=context,
            **kwargs,
        )


class DatabaseConnectionException(RextExternalServiceException):
    """Exception for database connection errors."""

    def __init__(
        self, message: str = "Database connection error", database_name: str = None, **kwargs
    ):
        super().__init__(
            message=message,
            service_name=database_name or "database",
            error_code=ErrorCode.DATABASE_CONNECTION_ERROR,
            status_code=503,
            severity=ErrorSeverity.HIGH,
            **kwargs,
        )


# ============================================================================
# DOMAIN-SPECIFIC EXCEPTIONS
# ============================================================================


class WorkspaceNotFoundException(ResourceNotFoundException):
    """Exception for workspace not found errors."""

    def __init__(self, workspace_id: str, **kwargs):
        super().__init__(resource_type="workspace", resource_id=workspace_id, **kwargs)


class WorkspaceAccessDeniedException(RextAuthorizationException):
    """Exception for workspace access denied errors."""

    def __init__(self, workspace_id: str, user_id: str = None, **kwargs):
        message = f"Access denied to workspace '{workspace_id}'"
        context = kwargs.get("context", {})
        context.update({"workspace_id": workspace_id, "user_id": user_id})

        super().__init__(
            message=message,
            error_code=ErrorCode.WORKSPACE_ACCESS_DENIED,
            resource=f"workspace:{workspace_id}",
            context=context,
            **kwargs,
        )


class KnowledgeProcessingException(RextBusinessException):
    """Exception for knowledge processing errors."""

    def __init__(
        self,
        message: str = "Knowledge processing failed",
        processing_stage: str = None,
        source_url: str = None,
        **kwargs,
    ):
        context = kwargs.get("context", {})
        context.update({"processing_stage": processing_stage, "source_url": source_url})

        super().__init__(
            message=message,
            error_code=ErrorCode.KNOWLEDGE_PROCESSING_FAILED,
            status_code=422,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs,
        )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def create_exception_from_error_code(
    error_code: ErrorCode, message: str, **kwargs
) -> RextAPIException:
    """
    Create an appropriate exception instance based on error code.

    Args:
        error_code: The error code to map
        message: Error message
        **kwargs: Additional exception parameters

    Returns:
        RextAPIException: Appropriate exception instance
    """
    exception_map = {
        ErrorCode.VALIDATION_FAILED: RextValidationException,
        ErrorCode.UNAUTHORIZED: RextAuthenticationException,
        ErrorCode.FORBIDDEN: RextAuthorizationException,
        ErrorCode.TOKEN_EXPIRED: TokenExpiredException,
        ErrorCode.API_KEY_INVALID: InvalidAPIKeyException,
        ErrorCode.RESOURCE_NOT_FOUND: ResourceNotFoundException,
        ErrorCode.DUPLICATE_RESOURCE: DuplicateResourceException,
        ErrorCode.BUSINESS_RULE_VIOLATION: BusinessRuleViolationException,
        ErrorCode.QUOTA_EXCEEDED: QuotaExceededException,
        ErrorCode.RATE_LIMIT_EXCEEDED: RateLimitExceededException,
        ErrorCode.EXTERNAL_SERVICE_ERROR: RextExternalServiceException,
        ErrorCode.EXTERNAL_SERVICE_TIMEOUT: ExternalServiceTimeoutException,
        ErrorCode.DATABASE_CONNECTION_ERROR: DatabaseConnectionException,
        ErrorCode.KNOWLEDGE_PROCESSING_FAILED: KnowledgeProcessingException,
    }

    exception_class = exception_map.get(error_code, RextAPIException)

    # Remove error_code from kwargs if present to avoid duplicate parameter
    kwargs.pop("error_code", None)

    return exception_class(message=message, **kwargs)
