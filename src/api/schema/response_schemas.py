"""
Response Schema Standards for Consistent API Responses

This module defines standardized response schemas using Pydantic for all API endpoints,
ensuring consistent response formats, proper error handling, and type safety across
the entire application.

Key Features:
- Consistent success/error response structure
- Comprehensive error classification
- Request tracking with unique IDs
- Metadata for debugging and analytics
- Type-safe response creation utilities

Usage:
    from src.api.schemas.response_schemas import create_success_response, create_error_response

    # Success response
    return create_success_response(
        data={"users": users_list},
        request_id=request_id
    )

    # Error response
    return create_error_response(
        code=ErrorCode.VALIDATION_FAILED,
        message="Invalid input data",
        status_code=422,
        request_id=request_id
    )
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")

# ============================================================================
# ENUMERATIONS
# ============================================================================


class ErrorSeverity(str, Enum):
    """Error severity levels for proper handling and alerting"""

    LOW = "low"  # Minor issues, user can continue
    MEDIUM = "medium"  # Moderate issues, requires attention
    HIGH = "high"  # Serious issues, blocks user workflow
    CRITICAL = "critical"  # System-level issues, requires immediate action


class ErrorCode(str, Enum):
    """Comprehensive error codes for consistent error handling"""

    # ========== VALIDATION ERRORS (4xx) ==========
    VALIDATION_FAILED = "validation_failed"
    MISSING_FIELD = "missing_field"
    INVALID_FORMAT = "invalid_format"
    INVALID_VALUE = "invalid_value"
    FIELD_TOO_LONG = "field_too_long"
    FIELD_TOO_SHORT = "field_too_short"
    INVALID_EMAIL_FORMAT = "invalid_email_format"
    INVALID_URL_FORMAT = "invalid_url_format"
    INVALID_DATE_FORMAT = "invalid_date_format"

    # ========== AUTHENTICATION & AUTHORIZATION ERRORS (401/403) ==========
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    ACCOUNT_DEACTIVATED = "account_deactivated"
    ACCOUNT_SUSPENDED = "account_suspended"
    ACCOUNT_BANNED = "account_banned"
    API_KEY_MISSING = "api_key_missing"
    API_KEY_INVALID = "api_key_invalid"

    # ========== BUSINESS LOGIC ERRORS (400/409/422) ==========
    RESOURCE_NOT_FOUND = "resource_not_found"
    RESOURCE_ALREADY_EXISTS = "resource_already_exists"
    DUPLICATE_RESOURCE = "duplicate_resource"
    BUSINESS_RULE_VIOLATION = "business_rule_violation"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    RESOURCE_LOCKED = "resource_locked"
    RESOURCE_IN_USE = "resource_in_use"
    QUOTA_EXCEEDED = "quota_exceeded"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

    # ========== EXTERNAL SERVICE ERRORS (502/503) ==========
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    EXTERNAL_SERVICE_TIMEOUT = "external_service_timeout"
    EXTERNAL_SERVICE_UNAVAILABLE = "external_service_unavailable"
    EXTERNAL_API_ERROR = "external_api_error"
    DATABASE_CONNECTION_ERROR = "database_connection_error"

    # ========== SYSTEM ERRORS (500) ==========
    INTERNAL_SERVER_ERROR = "internal_server_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    CONFIGURATION_ERROR = "configuration_error"
    DEPENDENCY_ERROR = "dependency_error"
    TIMEOUT_ERROR = "timeout_error"
    MEMORY_ERROR = "memory_error"
    DISK_SPACE_ERROR = "disk_space_error"

    # ========== WORKSPACE SPECIFIC ERRORS ==========
    WORKSPACE_NOT_FOUND = "workspace_not_found"
    WORKSPACE_ACCESS_DENIED = "workspace_access_denied"
    WORKSPACE_CREATION_FAILED = "workspace_creation_failed"
    WORKSPACE_UPDATE_FAILED = "workspace_update_failed"
    WORKSPACE_DELETION_FAILED = "workspace_deletion_failed"


# ============================================================================
# BASE MODELS
# ============================================================================


class ErrorDetail(BaseModel):
    """Detailed error information for field-level validation errors"""

    field: Optional[str] = Field(
        None,
        description="The field name that caused the error (for validation errors)",
        example="email",
    )
    message: str = Field(
        ..., description="Human-readable error message", example="Email format is invalid"
    )
    code: str = Field(
        ..., description="Machine-readable error code", example="invalid_email_format"
    )
    value: Optional[Any] = Field(
        None, description="The invalid value that caused the error (sanitized)"
    )


class ResponseMeta(BaseModel):
    """Metadata included in all responses for tracking and debugging"""

    request_id: str = Field(
        ..., description="Unique identifier for this request", example="req_1234567890_abc123"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISO timestamp when the response was generated",
        example="2024-01-15T10:30:00.123456Z",
    )
    processing_time_ms: Optional[int] = Field(
        None, description="Time taken to process the request in milliseconds", example=250, ge=0
    )
    version: str = Field(default="1.0", description="API version", example="1.0")
    server_id: Optional[str] = Field(
        None, description="Server instance identifier for debugging", example="server-01"
    )
    operation_id: Optional[str] = Field(
        None, description="Unique identifier for long-running operations", example="op_123456789"
    )

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, v):
        if not v or len(v) < 5:
            raise ValueError("request_id must be at least 5 characters long")
        return v


class BaseResponse(BaseModel):
    """Base response model with common fields"""

    success: bool = Field(..., description="Indicates whether the request was successful")
    message: Optional[str] = Field(
        default=None, description="Human-readable message describing the result"
    )
    meta: ResponseMeta = Field(..., description="Response metadata")


class SuccessResponse(BaseResponse, Generic[T]):
    """Standardized success response format"""

    success: bool = Field(default=True, description="Always true for success responses")
    data: T = Field(..., description="The response payload data")
    error: None = Field(default=None, description="Always null for success responses")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {},
                "error": None,
                "meta": {
                    "request_id": "req_1234567890_abc123",
                    "timestamp": "2024-01-15T10:30:00.123456Z",
                    "processing_time_ms": 250,
                    "version": "1.0",
                    "operation_id": None,
                },
            }
        }
    )


class ErrorResponse(BaseResponse):
    """Standardized error response format"""

    success: bool = Field(default=False, description="Always false for error responses")
    data: None = Field(default=None, description="Always null for error responses")
    error: Dict[str, Any] = Field(..., description="Error information object")

    @field_validator("error")
    @classmethod
    def validate_error_structure(cls, v):
        required_fields = ["code", "message", "severity", "status_code"]
        for field in required_fields:
            if field not in v:
                raise ValueError(f"Error object must contain {field}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "data": None,
                "error": {
                    "code": "validation_failed",
                    "message": "The request data failed validation",
                    "severity": "medium",
                    "status_code": 422,
                    "details": [
                        {
                            "field": "email",
                            "message": "Email format is invalid",
                            "code": "invalid_email_format",
                            "value": "invalid-email",
                        }
                    ],
                },
                "meta": {
                    "request_id": "req_1234567890_abc123",
                    "timestamp": "2024-01-15T10:30:00.123456Z",
                    "processing_time_ms": 150,
                    "version": "1.0",
                },
            }
        }
    )


class GenericResponse(BaseModel):
    """Simple generic response with success and message"""

    success: bool = Field(..., description="Indicates whether the operation was successful")
    message: str = Field(..., description="Human-readable message describing the result")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"success": True, "message": "Operation completed successfully"}
        }
    )


# ============================================================================
# TYPE UNIONS
# ============================================================================

StandardResponse = Union[SuccessResponse[Any], ErrorResponse]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def generate_request_id() -> str:
    """Generate a unique request ID"""
    timestamp = int(datetime.now(timezone.utc).timestamp())
    uuid_part = str(uuid4()).replace("-", "")[:8]
    return f"req_{timestamp}_{uuid_part}"


def create_success_response(
    data: T,
    message: Optional[str] = None,
    request_id: Optional[str] = None,
    processing_time_ms: Optional[int] = None,
    server_id: Optional[str] = None,
    operation_id: Optional[str] = None,
) -> SuccessResponse[T]:
    """
    Create a standardized success response.

    Args:
        data: The response payload data
        message: Optional human-readable message
        request_id: Optional request ID (auto-generated if not provided)
        processing_time_ms: Optional processing time in milliseconds
        server_id: Optional server instance identifier

    Returns:
        SuccessResponse: Standardized success response

    Example:
        >>> response = create_success_response(
        ...     data={"users": [{"id": "1", "name": "John"}]},
        ...     request_id="req_123",
        ...     processing_time_ms=150
        ... )
        >>> response.success
        True
    """
    return SuccessResponse(
        data=data,
        message=message,
        meta=ResponseMeta(
            request_id=request_id or generate_request_id(),
            processing_time_ms=processing_time_ms,
            server_id=server_id,
            operation_id=operation_id,
        ),
    )


def create_error_response(
    code: ErrorCode,
    message: str,
    status_code: int,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    details: Optional[List[ErrorDetail]] = None,
    request_id: Optional[str] = None,
    processing_time_ms: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
    server_id: Optional[str] = None,
    operation_id: Optional[str] = None,
) -> ErrorResponse:
    """
    Create a standardized error response.

    Args:
        code: Error code from ErrorCode enum
        message: Human-readable error message
        status_code: HTTP status code
        severity: Error severity level
        details: Optional list of detailed error information
        request_id: Optional request ID (auto-generated if not provided)
        processing_time_ms: Optional processing time in milliseconds
        context: Optional additional context for debugging
        server_id: Optional server instance identifier

    Returns:
        ErrorResponse: Standardized error response

    Example:
        >>> response = create_error_response(
        ...     code=ErrorCode.VALIDATION_FAILED,
        ...     message="Email is required",
        ...     status_code=422,
        ...     severity=ErrorSeverity.MEDIUM
        ... )
        >>> response.success
        False
    """
    error_data = {
        "code": code.value,
        "message": message,
        "severity": severity.value,
        "status_code": status_code,
    }

    if details:
        # Details might already be dicts (from exceptions) or Pydantic models
        error_data["details"] = [
            detail.model_dump() if hasattr(detail, "model_dump") else detail for detail in details
        ]

    if context:
        error_data["context"] = context

    return ErrorResponse(
        error=error_data,
        message=message,
        meta=ResponseMeta(
            request_id=request_id or generate_request_id(),
            processing_time_ms=processing_time_ms,
            server_id=server_id,
            operation_id=operation_id,
        ),
    )


def create_validation_error_response(
    message: str = "Validation failed",
    field_errors: Optional[Dict[str, List[str]]] = None,
    request_id: Optional[str] = None,
    processing_time_ms: Optional[int] = None,
) -> ErrorResponse:
    """
    Create a standardized validation error response.

    Args:
        message: Main error message
        field_errors: Dictionary of field names to lists of error messages
        request_id: Optional request ID (auto-generated if not provided)
        processing_time_ms: Optional processing time in milliseconds

    Returns:
        ErrorResponse: Standardized validation error response

    Example:
        >>> response = create_validation_error_response(
        ...     field_errors={
        ...         "email": ["Email is required", "Email format is invalid"],
        ...         "password": ["Password must be at least 8 characters"]
        ...     }
        ... )
        >>> len(response.error["details"])
        3
    """
    details = []

    if field_errors:
        for field, errors in field_errors.items():
            for error in errors:
                details.append(
                    ErrorDetail(field=field, message=error, code="field_validation_error")
                )

    return create_error_response(
        code=ErrorCode.VALIDATION_FAILED,
        message=message,
        status_code=422,
        severity=ErrorSeverity.MEDIUM,
        details=details,
        request_id=request_id,
        processing_time_ms=processing_time_ms,
    )


# ============================================================================
# ERROR CODE MAPPINGS
# ============================================================================


def get_error_code_for_http_status(status_code: int) -> ErrorCode:
    """
    Map HTTP status codes to appropriate error codes.

    Args:
        status_code: HTTP status code

    Returns:
        ErrorCode: Appropriate error code for the status
    """
    status_to_error_map = {
        400: ErrorCode.VALIDATION_FAILED,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.RESOURCE_NOT_FOUND,
        409: ErrorCode.DUPLICATE_RESOURCE,
        422: ErrorCode.VALIDATION_FAILED,
        429: ErrorCode.RATE_LIMIT_EXCEEDED,
        500: ErrorCode.INTERNAL_SERVER_ERROR,
        502: ErrorCode.EXTERNAL_SERVICE_ERROR,
        503: ErrorCode.SERVICE_UNAVAILABLE,
        504: ErrorCode.EXTERNAL_SERVICE_TIMEOUT,
    }

    return status_to_error_map.get(status_code, ErrorCode.INTERNAL_SERVER_ERROR)


def get_severity_for_http_status(status_code: int) -> ErrorSeverity:
    """
    Map HTTP status codes to appropriate error severity levels.

    Args:
        status_code: HTTP status code

    Returns:
        ErrorSeverity: Appropriate severity level
    """
    if status_code < 400:
        return ErrorSeverity.LOW
    elif status_code < 500:
        return ErrorSeverity.MEDIUM
    else:
        return ErrorSeverity.HIGH
