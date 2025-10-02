# API Middleware Package
#
# This package contains middleware components for the FastAPI application,
# including error handling, request tracking, and response processing.

from .error_handler import ErrorHandlerMiddleware, setup_exception_handlers
from .request_tracker import RequestTrackerMiddleware
from .permissions import (
    PermissionChecker,
    require_permissions,
    is_admin,
)
from .exceptions import (
    # Base exceptions
    WrextAPIException,
    WrextBusinessException,
    WrextValidationException,
    WrextAuthenticationException,
    WrextAuthorizationException,
    WrextExternalServiceException,

    # Specific exceptions
    ResourceNotFoundException,
    DuplicateResourceException,
    QuotaExceededException,
    RateLimitExceededException,
)

__all__ = [
    # Middleware classes
    "ErrorHandlerMiddleware",
    "RequestTrackerMiddleware",

    # Setup functions
    "setup_exception_handlers",

    # Permission checking
    "PermissionChecker",
    "require_permissions",
    "is_admin",

    # Exception classes
    "WrextAPIException",
    "WrextBusinessException",
    "WrextValidationException",
    "WrextAuthenticationException",
    "WrextAuthorizationException",
    "WrextExternalServiceException",
    "ResourceNotFoundException",
    "DuplicateResourceException",
    "QuotaExceededException",
    "RateLimitExceededException",
]