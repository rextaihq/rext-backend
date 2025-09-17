# API Middleware Package
#
# This package contains middleware components for the FastAPI application,
# including error handling, request tracking, and response processing.

from .error_handler import ErrorHandlerMiddleware, setup_exception_handlers
from .request_tracker import RequestTrackerMiddleware
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