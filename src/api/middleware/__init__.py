# API Middleware Package
#
# This package contains middleware components for the FastAPI application,
# including error handling, request tracking, and response processing.

from .error_handler import ErrorHandlerMiddleware, setup_exception_handlers
from .request_tracker import RequestTrackerMiddleware
from .rate_limiter import (
    RateLimiterMiddleware,
    login_rate_limit,
    password_reset_rate_limit,
    registration_rate_limit,
    email_verification_rate_limit,
)
from .permissions import (
    PermissionChecker,
    require_permissions,
    is_admin,
)
from .exceptions import (
    # Base exceptions
    RextAPIException,
    RextBusinessException,
    RextValidationException,
    RextAuthenticationException,
    RextAuthorizationException,
    RextExternalServiceException,

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
    "RateLimiterMiddleware",

    # Setup functions
    "setup_exception_handlers",

    # Rate limiting
    "login_rate_limit",
    "password_reset_rate_limit",
    "registration_rate_limit",
    "email_verification_rate_limit",

    # Permission checking
    "PermissionChecker",
    "require_permissions",
    "is_admin",

    # Exception classes
    "RextAPIException",
    "RextBusinessException",
    "RextValidationException",
    "RextAuthenticationException",
    "RextAuthorizationException",
    "RextExternalServiceException",
    "ResourceNotFoundException",
    "DuplicateResourceException",
    "QuotaExceededException",
    "RateLimitExceededException",
]