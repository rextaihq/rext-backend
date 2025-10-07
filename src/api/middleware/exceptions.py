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


class WrextAPIException(Exception):
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
        context: Optional[Dict[str, Any]] = None
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
            "context": self.context
        }


# ============================================================================
# VALIDATION EXCEPTIONS (4xx)
# ============================================================================

class WrextValidationException(WrextAPIException):
    """Exception for validation errors."""

    def __init__(
        self,
        message: str = "Validation failed",
        field_errors: Optional[Dict[str, List[str]]] = None,
        **kwargs
    ):
        details = []
        if field_errors:
            for field, errors in field_errors.items():
                for error in errors:
                    details.append({
                        "field": field,
                        "message": error,
                        "code": "field_validation_error"
                    })

        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_FAILED,
            status_code=422,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            **kwargs
        )


class InvalidFormatException(WrextValidationException):
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
                "received_value": str(received_value) if received_value else None
            }
        )


# ============================================================================
# AUTHENTICATION & AUTHORIZATION EXCEPTIONS (401/403)
# ============================================================================

class WrextAuthenticationException(WrextAPIException):
    """Exception for authentication errors."""

    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(
            message=message,
            error_code=ErrorCode.UNAUTHORIZED,
            status_code=401,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class WrextAuthorizationException(WrextAPIException):
    """Exception for authorization errors."""

    def __init__(self, message: str = "Access forbidden", resource: str = None, **kwargs):
        context = kwargs.get('context', {})
        if resource:
            context['resource'] = resource

        super().__init__(
            message=message,
            error_code=ErrorCode.FORBIDDEN,
            status_code=403,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs
        )


class TokenExpiredException(WrextAuthenticationException):
    """Exception for expired authentication tokens."""

    def __init__(self, message: str = "Authentication token has expired"):
        super().__init__(
            message=message,
            error_code=ErrorCode.TOKEN_EXPIRED,
            context={"suggestion": "Please refresh your token or log in again"}
        )


class InvalidAPIKeyException(WrextAuthenticationException):
    """Exception for invalid API key errors."""

    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(
            message=message,
            context={"suggestion": "Please check your API key configuration"}
        )


# ============================================================================
# BUSINESS LOGIC EXCEPTIONS (400/404/409)
# ============================================================================

class WrextBusinessException(WrextAPIException):
    """Base class for business logic related exceptions."""
    pass


class ResourceNotFoundException(WrextBusinessException):
    """Exception for when a requested resource is not found."""

    def __init__(
        self,
        message: str = None,
        resource_type: str = "resource",
        resource_id: str = None,
        **kwargs
    ):
        if not message:
            if resource_id:
                message = f"{resource_type.title()} with ID '{resource_id}' not found"
            else:
                message = f"{resource_type.title()} not found"

        context = kwargs.pop('context', {})  # Use pop to remove from kwargs
        context.update({
            "resource_type": resource_type,
            "resource_id": resource_id
        })

        super().__init__(
            message=message,
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            severity=ErrorSeverity.LOW,
            context=context,
            **kwargs
        )


class DuplicateResourceException(WrextBusinessException):
    """Exception for when trying to create a resource that already exists."""

    def __init__(
        self,
        message: str = None,
        resource_type: str = "resource",
        conflicting_field: str = None,
        conflicting_value: str = None,
        **kwargs
    ):
        if not message:
            if conflicting_field and conflicting_value:
                message = f"{resource_type.title()} with {conflicting_field} '{conflicting_value}' already exists"
            else:
                message = f"{resource_type.title()} already exists"

        context = kwargs.pop('context', {})
        context.update({
            "resource_type": resource_type,
            "conflicting_field": conflicting_field,
            "conflicting_value": conflicting_value
        })

        super().__init__(
            message=message,
            error_code=ErrorCode.DUPLICATE_RESOURCE,
            status_code=409,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs
        )


class BusinessRuleViolationException(WrextBusinessException):
    """Exception for business rule violations."""

    def __init__(
        self,
        message: str,
        rule_name: str = None,
        **kwargs
    ):
        context = kwargs.get('context', {})
        if rule_name:
            context['rule_name'] = rule_name

        super().__init__(
            message=message,
            error_code=ErrorCode.BUSINESS_RULE_VIOLATION,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs
        )


class QuotaExceededException(WrextBusinessException):
    """Exception for quota/limit exceeded errors."""

    def __init__(
        self,
        message: str = "Quota exceeded",
        quota_type: str = None,
        current_value: int = None,
        limit_value: int = None,
        **kwargs
    ):
        context = kwargs.get('context', {})
        context.update({
            "quota_type": quota_type,
            "current_value": current_value,
            "limit_value": limit_value
        })

        super().__init__(
            message=message,
            error_code=ErrorCode.QUOTA_EXCEEDED,
            status_code=400,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs
        )


class RateLimitExceededException(WrextBusinessException):
    """Exception for rate limit exceeded errors."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int = None,
        **kwargs
    ):
        context = kwargs.get('context', {})
        if retry_after:
            context['retry_after_seconds'] = retry_after
            message += f". Try again in {retry_after} seconds"

        super().__init__(
            message=message,
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=429,
            severity=ErrorSeverity.LOW,
            context=context,
            **kwargs
        )


# ============================================================================
# EXTERNAL SERVICE EXCEPTIONS (502/503)
# ============================================================================

class WrextExternalServiceException(WrextAPIException):
    """Exception for external service related errors."""

    def __init__(
        self,
        message: str,
        service_name: str = None,
        service_error: str = None,
        **kwargs
    ):
        context = kwargs.get('context', {})
        context.update({
            "service_name": service_name,
            "service_error": service_error
        })

        super().__init__(
            message=message,
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=502,
            severity=ErrorSeverity.HIGH,
            context=context,
            **kwargs
        )


class ExternalServiceTimeoutException(WrextExternalServiceException):
    """Exception for external service timeout errors."""

    def __init__(
        self,
        service_name: str,
        timeout_seconds: int = None,
        **kwargs
    ):
        message = f"Timeout communicating with {service_name}"
        if timeout_seconds:
            message += f" after {timeout_seconds} seconds"

        context = kwargs.get('context', {})
        context.update({
            "timeout_seconds": timeout_seconds
        })

        super().__init__(
            message=message,
            service_name=service_name,
            error_code=ErrorCode.EXTERNAL_SERVICE_TIMEOUT,
            status_code=504,
            context=context,
            **kwargs
        )


class DatabaseConnectionException(WrextExternalServiceException):
    """Exception for database connection errors."""

    def __init__(
        self,
        message: str = "Database connection error",
        database_name: str = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            service_name=database_name or "database",
            error_code=ErrorCode.DATABASE_CONNECTION_ERROR,
            status_code=503,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )


# ============================================================================
# DOMAIN-SPECIFIC EXCEPTIONS
# ============================================================================

class TopicGenerationException(WrextBusinessException):
    """Exception for topic generation specific errors."""

    def __init__(
        self,
        message: str = "Topic generation failed",
        generation_params: Dict[str, Any] = None,
        **kwargs
    ):
        context = kwargs.get('context', {})
        if generation_params:
            context['generation_params'] = generation_params

        super().__init__(
            message=message,
            error_code=ErrorCode.TOPIC_GENERATION_FAILED,
            status_code=422,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs
        )


class WorkspaceNotFoundException(ResourceNotFoundException):
    """Exception for workspace not found errors."""

    def __init__(self, workspace_id: str, **kwargs):
        super().__init__(
            resource_type="workspace",
            resource_id=workspace_id,
            **kwargs
        )


class WorkspaceAccessDeniedException(WrextAuthorizationException):
    """Exception for workspace access denied errors."""

    def __init__(self, workspace_id: str, user_id: str = None, **kwargs):
        message = f"Access denied to workspace '{workspace_id}'"
        context = kwargs.get('context', {})
        context.update({
            "workspace_id": workspace_id,
            "user_id": user_id
        })

        super().__init__(
            message=message,
            error_code=ErrorCode.WORKSPACE_ACCESS_DENIED,
            resource=f"workspace:{workspace_id}",
            context=context,
            **kwargs
        )


class KnowledgeProcessingException(WrextBusinessException):
    """Exception for knowledge processing errors."""

    def __init__(
        self,
        message: str = "Knowledge processing failed",
        processing_stage: str = None,
        source_url: str = None,
        **kwargs
    ):
        context = kwargs.get('context', {})
        context.update({
            "processing_stage": processing_stage,
            "source_url": source_url
        })

        super().__init__(
            message=message,
            error_code=ErrorCode.KNOWLEDGE_PROCESSING_FAILED,
            status_code=422,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            **kwargs
        )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_exception_from_error_code(
    error_code: ErrorCode,
    message: str,
    **kwargs
) -> WrextAPIException:
    """
    Create an appropriate exception instance based on error code.

    Args:
        error_code: The error code to map
        message: Error message
        **kwargs: Additional exception parameters

    Returns:
        WrextAPIException: Appropriate exception instance
    """
    exception_map = {
        ErrorCode.VALIDATION_FAILED: WrextValidationException,
        ErrorCode.UNAUTHORIZED: WrextAuthenticationException,
        ErrorCode.FORBIDDEN: WrextAuthorizationException,
        ErrorCode.TOKEN_EXPIRED: TokenExpiredException,
        ErrorCode.API_KEY_INVALID: InvalidAPIKeyException,
        ErrorCode.RESOURCE_NOT_FOUND: ResourceNotFoundException,
        ErrorCode.DUPLICATE_RESOURCE: DuplicateResourceException,
        ErrorCode.BUSINESS_RULE_VIOLATION: BusinessRuleViolationException,
        ErrorCode.QUOTA_EXCEEDED: QuotaExceededException,
        ErrorCode.RATE_LIMIT_EXCEEDED: RateLimitExceededException,
        ErrorCode.EXTERNAL_SERVICE_ERROR: WrextExternalServiceException,
        ErrorCode.EXTERNAL_SERVICE_TIMEOUT: ExternalServiceTimeoutException,
        ErrorCode.DATABASE_CONNECTION_ERROR: DatabaseConnectionException,
        ErrorCode.TOPIC_GENERATION_FAILED: TopicGenerationException,
        ErrorCode.KNOWLEDGE_PROCESSING_FAILED: KnowledgeProcessingException,
    }

    exception_class = exception_map.get(error_code, WrextAPIException)

    # Remove error_code from kwargs if present to avoid duplicate parameter
    kwargs.pop('error_code', None)

    return exception_class(message=message, **kwargs)