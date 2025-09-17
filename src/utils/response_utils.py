"""
Response Utilities for Consistent API Responses

This module provides utility functions and decorators for creating consistent
API responses throughout the application. It integrates with the response
schema standards and simplifies response creation in route handlers.

Features:
- Standardized response creation functions
- Automatic request tracking integration
- Pagination response utilities
- Response validation helpers
- Decorators for common response patterns
- Error response helpers with context
"""

import functools
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Callable, TypeVar, Generic
from uuid import uuid4

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.schema.response_schemas import (
    SuccessResponse,
    ErrorResponse,
    ErrorCode,
    ErrorSeverity,
    ErrorDetail,
    create_success_response,
    create_error_response,
    create_validation_error_response,
)
from src.api.middleware.exceptions import (
    WrextAPIException,
    ResourceNotFoundException,
    DuplicateResourceException,
    WrextValidationException,
)
from src.api.middleware.request_tracker import get_request_id


# ============================================================================
# CUSTOM JSON ENCODER
# ============================================================================

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            # Convert to ISO format with Z suffix if no timezone info
            if obj.tzinfo is None:
                return obj.isoformat() + 'Z'
            return obj.isoformat()
        return super().default(obj)


# ============================================================================
# TYPE DEFINITIONS
# ============================================================================

T = TypeVar('T')
ResponseData = Union[Dict[str, Any], List[Any], BaseModel, Any]


class PaginationMeta(BaseModel):
    """Metadata for paginated responses."""

    page: int = 1
    per_page: int = 20
    total_items: int = 0
    total_pages: int = 0
    has_next: bool = False
    has_previous: bool = False

    @classmethod
    def from_query_params(
        cls,
        page: int = 1,
        per_page: int = 20,
        total_items: int = 0
    ) -> "PaginationMeta":
        """Create pagination metadata from query parameters."""
        total_pages = max(1, (total_items + per_page - 1) // per_page)

        return cls(
            page=max(1, page),
            per_page=max(1, min(per_page, 100)),  # Limit max per_page
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1
        )


class PaginatedData(BaseModel, Generic[T]):
    """Generic paginated response data."""

    items: List[T]
    pagination: PaginationMeta

    class Config:
        arbitrary_types_allowed = True


# ============================================================================
# BASIC RESPONSE FUNCTIONS
# ============================================================================

def success(
    data: ResponseData,
    request: Optional[Request] = None,
    message: Optional[str] = None,
    status_code: int = 200
) -> JSONResponse:
    """
    Create a standardized success response.

    Args:
        data: Response payload data
        request: FastAPI request object for tracking
        message: Optional success message
        status_code: HTTP status code (default: 200)

    Returns:
        JSONResponse: Standardized success response

    Example:
        >>> return success(
        ...     data={"users": user_list},
        ...     request=request,
        ...     message="Users retrieved successfully"
        ... )
    """
    # Extract request tracking info
    request_id = get_request_id(request) if request else None
    processing_time_ms = None

    if request and hasattr(request.state, '_start_time'):
        processing_time_ms = int((time.time() - request.state._start_time) * 1000)

    # Add message to data if provided
    response_data = data
    if message:
        if isinstance(data, dict):
            response_data = {"message": message, **data}
        else:
            response_data = {"message": message, "data": data}

    # Create response
    response = create_success_response(
        data=response_data,
        request_id=request_id,
        processing_time_ms=processing_time_ms
    )

    return JSONResponse(
        status_code=status_code,
        content=json.loads(json.dumps(response.model_dump(), cls=DateTimeEncoder))
    )


def error(
    message: str,
    code: ErrorCode = ErrorCode.INTERNAL_SERVER_ERROR,
    status_code: int = 500,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    details: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    """
    Create a standardized error response.

    Args:
        message: Error message
        code: Error code from ErrorCode enum
        status_code: HTTP status code
        severity: Error severity level
        details: Optional error details
        context: Optional error context
        request: FastAPI request object for tracking

    Returns:
        JSONResponse: Standardized error response
    """
    request_id = get_request_id(request) if request else None
    processing_time_ms = None

    if request and hasattr(request.state, '_start_time'):
        processing_time_ms = int((time.time() - request.state._start_time) * 1000)

    # Convert details to ErrorDetail objects if needed
    error_details = None
    if details:
        error_details = [
            ErrorDetail(**detail) if isinstance(detail, dict) else detail
            for detail in details
        ]

    response = create_error_response(
        code=code,
        message=message,
        status_code=status_code,
        severity=severity,
        details=error_details,
        context=context,
        request_id=request_id,
        processing_time_ms=processing_time_ms
    )

    return JSONResponse(
        status_code=status_code,
        content=json.loads(json.dumps(response.model_dump(), cls=DateTimeEncoder))
    )


def validation_error(
    message: str = "Validation failed",
    field_errors: Optional[Dict[str, List[str]]] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    """
    Create a standardized validation error response.

    Args:
        message: Main validation error message
        field_errors: Dictionary of field names to error lists
        request: FastAPI request object for tracking

    Returns:
        JSONResponse: Standardized validation error response
    """
    request_id = get_request_id(request) if request else None
    processing_time_ms = None

    if request and hasattr(request.state, '_start_time'):
        processing_time_ms = int((time.time() - request.state._start_time) * 1000)

    response = create_validation_error_response(
        message=message,
        field_errors=field_errors,
        request_id=request_id,
        processing_time_ms=processing_time_ms
    )

    return JSONResponse(
        status_code=422,
        content=json.loads(json.dumps(response.model_dump(), cls=DateTimeEncoder))
    )


# ============================================================================
# SPECIALIZED RESPONSE FUNCTIONS
# ============================================================================

def created(
    data: ResponseData,
    request: Optional[Request] = None,
    message: str = "Resource created successfully",
    location: Optional[str] = None
) -> JSONResponse:
    """
    Create a standardized 201 Created response.

    Args:
        data: Created resource data
        request: FastAPI request object
        message: Success message
        location: Optional Location header value

    Returns:
        JSONResponse: 201 Created response
    """
    response = success(
        data=data,
        request=request,
        message=message,
        status_code=201
    )

    if location:
        response.headers["Location"] = location

    return response


def accepted(
    data: Optional[ResponseData] = None,
    request: Optional[Request] = None,
    message: str = "Request accepted for processing"
) -> JSONResponse:
    """
    Create a standardized 202 Accepted response.

    Args:
        data: Optional response data
        request: FastAPI request object
        message: Acceptance message

    Returns:
        JSONResponse: 202 Accepted response
    """
    response_data = data or {"status": "accepted"}

    return success(
        data=response_data,
        request=request,
        message=message,
        status_code=202
    )


def no_content(request: Optional[Request] = None) -> JSONResponse:
    """
    Create a standardized 204 No Content response.

    Args:
        request: FastAPI request object

    Returns:
        JSONResponse: 204 No Content response
    """
    request_id = get_request_id(request) if request else None
    processing_time_ms = None

    if request and hasattr(request.state, '_start_time'):
        processing_time_ms = int((time.time() - request.state._start_time) * 1000)

    response = create_success_response(
        data=None,
        request_id=request_id,
        processing_time_ms=processing_time_ms
    )

    return JSONResponse(
        status_code=204,
        content=json.loads(json.dumps(response.model_dump(), cls=DateTimeEncoder))
    )


def not_found(
    resource_type: str = "resource",
    resource_id: Optional[str] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    """
    Create a standardized 404 Not Found response.

    Args:
        resource_type: Type of resource that wasn't found
        resource_id: ID of the resource that wasn't found
        request: FastAPI request object

    Returns:
        JSONResponse: 404 Not Found response
    """
    message = f"{resource_type.title()} not found"
    if resource_id:
        message = f"{resource_type.title()} with ID '{resource_id}' not found"

    context = {
        "resource_type": resource_type,
        "resource_id": resource_id
    }

    return error(
        message=message,
        code=ErrorCode.RESOURCE_NOT_FOUND,
        status_code=404,
        severity=ErrorSeverity.LOW,
        context=context,
        request=request
    )


def conflict(
    message: str = "Resource already exists",
    conflicting_field: Optional[str] = None,
    conflicting_value: Optional[str] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    """
    Create a standardized 409 Conflict response.

    Args:
        message: Conflict error message
        conflicting_field: Field that caused the conflict
        conflicting_value: Value that caused the conflict
        request: FastAPI request object

    Returns:
        JSONResponse: 409 Conflict response
    """
    context = {}
    if conflicting_field:
        context["conflicting_field"] = conflicting_field
    if conflicting_value:
        context["conflicting_value"] = conflicting_value

    return error(
        message=message,
        code=ErrorCode.DUPLICATE_RESOURCE,
        status_code=409,
        severity=ErrorSeverity.MEDIUM,
        context=context,
        request=request
    )


def unauthorized(
    message: str = "Authentication required",
    request: Optional[Request] = None
) -> JSONResponse:
    """
    Create a standardized 401 Unauthorized response.

    Args:
        message: Authentication error message
        request: FastAPI request object

    Returns:
        JSONResponse: 401 Unauthorized response
    """
    return error(
        message=message,
        code=ErrorCode.UNAUTHORIZED,
        status_code=401,
        severity=ErrorSeverity.MEDIUM,
        request=request
    )


def forbidden(
    message: str = "Access forbidden",
    resource: Optional[str] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    """
    Create a standardized 403 Forbidden response.

    Args:
        message: Forbidden error message
        resource: Resource that access was denied to
        request: FastAPI request object

    Returns:
        JSONResponse: 403 Forbidden response
    """
    context = {"resource": resource} if resource else None

    return error(
        message=message,
        code=ErrorCode.FORBIDDEN,
        status_code=403,
        severity=ErrorSeverity.MEDIUM,
        context=context,
        request=request
    )


# ============================================================================
# PAGINATION UTILITIES
# ============================================================================

def paginated_success(
    items: List[Any],
    pagination: PaginationMeta,
    request: Optional[Request] = None,
    message: Optional[str] = None
) -> JSONResponse:
    """
    Create a paginated success response.

    Args:
        items: List of items for current page
        pagination: Pagination metadata
        request: FastAPI request object
        message: Optional success message

    Returns:
        JSONResponse: Paginated success response
    """
    data = {
        "items": items,
        "pagination": json.loads(json.dumps(pagination.model_dump(), cls=DateTimeEncoder))
    }

    return success(
        data=data,
        request=request,
        message=message
    )


def create_pagination_meta(
    page: int,
    per_page: int,
    total_items: int
) -> PaginationMeta:
    """
    Create pagination metadata.

    Args:
        page: Current page number (1-based)
        per_page: Items per page
        total_items: Total number of items

    Returns:
        PaginationMeta: Pagination metadata
    """
    return PaginationMeta.from_query_params(
        page=page,
        per_page=per_page,
        total_items=total_items
    )


def get_pagination_params(
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    max_per_page: int = 100
) -> tuple[int, int, int]:
    """
    Get validated pagination parameters.

    Args:
        page: Requested page number
        per_page: Requested items per page
        max_per_page: Maximum allowed items per page

    Returns:
        tuple: (page, per_page, offset) for database queries
    """
    # Validate and default parameters
    page = max(1, page or 1)
    per_page = max(1, min(per_page or 20, max_per_page))
    offset = (page - 1) * per_page

    return page, per_page, offset


# ============================================================================
# RESPONSE DECORATORS
# ============================================================================

def response_handler(
    success_message: Optional[str] = None,
    error_message: Optional[str] = None,
    success_status: int = 200
):
    """
    Decorator for automatic response handling.

    Args:
        success_message: Optional success message
        error_message: Optional error message prefix
        success_status: HTTP status code for success

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from arguments
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            # Look for request in kwargs
            if not request:
                request = kwargs.get('request')

            try:
                # Call the original function
                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)

                # Handle different return types
                if isinstance(result, JSONResponse):
                    return result
                elif isinstance(result, (dict, list, BaseModel)):
                    return success(
                        data=result,
                        request=request,
                        message=success_message,
                        status_code=success_status
                    )
                else:
                    return success(
                        data={"result": result},
                        request=request,
                        message=success_message,
                        status_code=success_status
                    )

            except WrextAPIException:
                # Re-raise custom exceptions to be handled by middleware
                raise
            except HTTPException:
                # Re-raise HTTP exceptions to be handled by middleware
                raise
            except Exception as e:
                # Convert unexpected exceptions to standardized error
                message = f"{error_message}: {str(e)}" if error_message else str(e)
                return error(
                    message=message,
                    code=ErrorCode.INTERNAL_SERVER_ERROR,
                    status_code=500,
                    severity=ErrorSeverity.HIGH,
                    request=request
                )

        return wrapper
    return decorator


def paginated_response(
    success_message: Optional[str] = None,
    max_per_page: int = 100
):
    """
    Decorator for automatic paginated response handling.

    Args:
        success_message: Optional success message
        max_per_page: Maximum items per page

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if not request:
                request = kwargs.get('request')

            try:
                # Extract pagination parameters from query string
                query_params = request.query_params if request else {}
                page = int(query_params.get('page', 1))
                per_page = int(query_params.get('per_page', 20))

                # Validate pagination parameters
                page, per_page, offset = get_pagination_params(page, per_page, max_per_page)

                # Add pagination parameters to kwargs
                kwargs.update({
                    'page': page,
                    'per_page': per_page,
                    'offset': offset
                })

                # Call the original function
                result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)

                # Expected result format: (items, total_count)
                if isinstance(result, tuple) and len(result) == 2:
                    items, total_count = result
                    pagination = create_pagination_meta(page, per_page, total_count)

                    return paginated_success(
                        items=items,
                        pagination=pagination,
                        request=request,
                        message=success_message
                    )
                else:
                    # Fallback to regular success response
                    return success(
                        data=result,
                        request=request,
                        message=success_message
                    )

            except WrextAPIException:
                raise
            except HTTPException:
                raise
            except Exception as e:
                return error(
                    message=f"Pagination error: {str(e)}",
                    code=ErrorCode.INTERNAL_SERVER_ERROR,
                    status_code=500,
                    severity=ErrorSeverity.HIGH,
                    request=request
                )

        return wrapper
    return decorator


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> None:
    """
    Validate that required fields are present in data.

    Args:
        data: Data dictionary to validate
        required_fields: List of required field names

    Raises:
        WrextValidationException: If any required fields are missing
    """
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]

    if missing_fields:
        field_errors = {field: ["This field is required"] for field in missing_fields}
        raise WrextValidationException(
            message=f"Missing required fields: {', '.join(missing_fields)}",
            field_errors=field_errors
        )


def validate_field_length(
    data: Dict[str, Any],
    field_rules: Dict[str, Dict[str, int]]
) -> None:
    """
    Validate field lengths according to rules.

    Args:
        data: Data dictionary to validate
        field_rules: Dictionary of field names to length rules
                    Format: {"field": {"min": 1, "max": 100}}

    Raises:
        WrextValidationException: If any field length validation fails
    """
    field_errors = {}

    for field_name, rules in field_rules.items():
        if field_name in data and data[field_name] is not None:
            value = str(data[field_name])
            min_length = rules.get('min', 0)
            max_length = rules.get('max')

            errors = []
            if len(value) < min_length:
                errors.append(f"Must be at least {min_length} characters long")
            if max_length and len(value) > max_length:
                errors.append(f"Must be no more than {max_length} characters long")

            if errors:
                field_errors[field_name] = errors

    if field_errors:
        raise WrextValidationException(
            message="Field length validation failed",
            field_errors=field_errors
        )


# Import asyncio for coroutine detection
import asyncio