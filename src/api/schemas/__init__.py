# API Schemas Package
#
# This package contains all Pydantic models for API request and response schemas,
# providing consistent data validation and serialization across all endpoints.

from .response_schemas import (
    # Base response types
    StandardResponse,
    SuccessResponse,
    ErrorResponse,
    ResponseMeta,

    # Error handling types
    ErrorDetail,
    ErrorCode,
    ErrorSeverity,
    ResponseStatus,

    # Utility functions
    create_success_response,
    create_error_response,
    create_validation_error_response,
)

__all__ = [
    # Response types
    "StandardResponse",
    "SuccessResponse",
    "ErrorResponse",
    "ResponseMeta",

    # Error types
    "ErrorDetail",
    "ErrorCode",
    "ErrorSeverity",
    "ResponseStatus",

    # Utility functions
    "create_success_response",
    "create_error_response",
    "create_validation_error_response",
]