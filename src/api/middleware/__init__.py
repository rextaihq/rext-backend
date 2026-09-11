# API Middleware Package
#
# This package contains middleware components for the FastAPI application,
# including error handling, request tracking, and response processing.

from .error_handler import ErrorHandlerMiddleware, setup_exception_handlers
from .exceptions import (
    DuplicateResourceException,
    QuotaExceededException,
    RateLimitExceededException,
    # Specific exceptions
    ResourceNotFoundException,
    # Base exceptions
    RextAPIException,
    RextAuthenticationException,
    RextAuthorizationException,
    RextBusinessException,
    RextExternalServiceException,
    RextValidationException,
)
from .permissions import (
    PermissionChecker,
    is_admin,
    require_permissions,
)
from .rate_limiter import (
    RateLimiterMiddleware,
    email_verification_rate_limit,
    login_rate_limit,
    media_upload_rate_limit,
    password_reset_rate_limit,
    registration_rate_limit,
)
from .request_tracker import RequestTrackerMiddleware

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
    "media_upload_rate_limit",
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
