# Consistent Response and Error Handling System

This document explains the new consistent response and error handling system implemented in the Wrext backend API.

## 🎯 Overview

The system provides:
- **Standardized response formats** for all API endpoints
- **Comprehensive error handling** with detailed error information
- **Request tracking** with unique correlation IDs
- **Automatic error classification** and recovery suggestions
- **Performance monitoring** with processing time tracking
- **Security-aware** error message filtering

## 📐 Response Format

### Success Response
```json
{
  "success": true,
  "data": {
    "users": [{"id": "1", "name": "John"}],
    "total_count": 1
  },
  "error": null,
  "meta": {
    "request_id": "req_1704067200_abc123",
    "timestamp": "2024-01-01T00:00:00.000Z",
    "processing_time_ms": 150,
    "version": "1.0"
  }
}
```

### Error Response
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "validation_failed",
    "message": "Validation failed with 2 error(s)",
    "severity": "medium",
    "status_code": 422,
    "details": [
      {
        "field": "email",
        "message": "Email format is invalid",
        "code": "invalid_email_format",
        "value": null
      }
    ]
  },
  "meta": {
    "request_id": "req_1704067200_def456",
    "timestamp": "2024-01-01T00:00:00.000Z",
    "processing_time_ms": 75,
    "version": "1.0"
  }
}
```

## 🛠 Implementation Components

### 1. Response Schemas (`src/api/schemas/response_schemas.py`)

#### Core Models
- `SuccessResponse` - Standardized success response format
- `ErrorResponse` - Standardized error response format
- `ResponseMeta` - Metadata included in all responses
- `ErrorDetail` - Detailed error information for validation errors

#### Error Classification
- `ErrorCode` - Comprehensive error codes enum
- `ErrorSeverity` - Error severity levels (low/medium/high/critical)

#### Utility Functions
```python
from src.api.schemas.response_schemas import (
    create_success_response,
    create_error_response,
    create_validation_error_response
)

# Create success response
response = create_success_response(
    data={"users": users_list},
    request_id="req_123"
)

# Create error response
response = create_error_response(
    code=ErrorCode.VALIDATION_FAILED,
    message="Invalid input data",
    status_code=422,
    request_id="req_123"
)
```

### 2. Custom Exceptions (`src/api/middleware/exceptions.py`)

#### Base Exception
```python
from src.api.middleware.exceptions import WrextAPIException

class WrextAPIException(Exception):
    def __init__(self, message, error_code, status_code, severity, details=None):
        # Exception with structured error information
```

#### Specialized Exceptions
```python
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    DuplicateResourceException,
    WrextValidationException,
    TopicGenerationException,
    WorkspaceNotFoundException
)

# Usage in route handlers
if not user:
    raise ResourceNotFoundException(
        resource_type="user",
        resource_id=user_id
    )

if existing_workspace:
    raise DuplicateResourceException(
        resource_type="workspace",
        conflicting_field="title",
        conflicting_value=title
    )
```

### 3. Response Utilities (`src/utils/response_utils.py`)

#### Helper Functions
```python
from src.utils.response_utils import success, error, created, not_found

# Success response
return success(
    data={"users": users_list},
    request=request,
    message="Users retrieved successfully"
)

# Error response
return error(
    message="Failed to create user",
    code=ErrorCode.INTERNAL_SERVER_ERROR,
    status_code=500,
    request=request
)

# Created response (201)
return created(
    data={"user": new_user},
    request=request,
    message="User created successfully"
)

# Not found response (404)
return not_found(
    resource_type="user",
    resource_id=user_id,
    request=request
)
```

#### Response Decorators
```python
from src.utils.response_utils import response_handler, paginated_response

@response_handler(
    success_message="Users retrieved successfully",
    success_status=200
)
def get_users(request: Request, db: Session):
    users = db.query(User).all()
    return {"users": users}  # Automatically wrapped in success response

@paginated_response(success_message="Topics retrieved successfully")
def get_topics(request: Request, db: Session, page: int, per_page: int, offset: int):
    topics = db.query(Topics).offset(offset).limit(per_page).all()
    total = db.query(Topics).count()
    return topics, total  # Automatically formatted as paginated response
```

### 4. Request Tracking (`src/api/middleware/request_tracker.py`)

#### Features
- Automatic request ID generation
- Client-provided request ID support
- Processing time tracking
- Request correlation logging

#### Configuration
```python
app.add_middleware(
    RequestTrackerMiddleware,
    header_name="X-Request-ID",
    generate_if_missing=True,
    log_requests=True,
    include_processing_time=True
)
```

### 5. Error Handler (`src/api/middleware/error_handler.py`)

#### Features
- Automatic exception conversion to standardized responses
- Request ID correlation for error tracking
- Security-conscious error message filtering
- Comprehensive error logging

#### Configuration
```python
app.add_middleware(
    ErrorHandlerMiddleware,
    include_debug_info=False,  # Set to True in development
    log_full_traceback=True,
    filter_sensitive_data=True,
    max_error_details=10
)
```

## 🚀 Usage Examples

### Route Handler Examples

#### Basic Route with Error Handling
```python
from fastapi import APIRouter, Request, Depends
from src.utils.response_utils import success, not_found
from src.api.middleware.exceptions import ResourceNotFoundException

@router.get("/users/{user_id}")
def get_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise ResourceNotFoundException(
            resource_type="user",
            resource_id=user_id
        )

    return success(
        data={"user": user.to_dict()},
        request=request,
        message="User retrieved successfully"
    )
```

#### Route with Validation
```python
from src.api.middleware.exceptions import WrextValidationException

@router.post("/users")
def create_user(user_data: UserSchema, request: Request, db: Session = Depends(get_db)):
    # Check for duplicate email
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise DuplicateResourceException(
            resource_type="user",
            conflicting_field="email",
            conflicting_value=user_data.email
        )

    # Create user
    user = User(**user_data.dict())
    db.add(user)
    db.commit()

    return created(
        data={"user": user.to_dict()},
        request=request,
        message="User created successfully"
    )
```

#### Route with Custom Business Logic Error
```python
from src.api.middleware.exceptions import BusinessRuleViolationException

@router.post("/workspaces/{workspace_id}/generate-topics")
def generate_topics(workspace_id: str, request: Request, db: Session = Depends(get_db)):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()

    if not workspace:
        raise ResourceNotFoundException(
            resource_type="workspace",
            resource_id=workspace_id
        )

    # Check business rule
    if workspace.topic_count >= workspace.max_topics:
        raise BusinessRuleViolationException(
            message="Workspace has reached maximum topic limit",
            rule_name="max_topics_per_workspace",
            context={
                "current_count": workspace.topic_count,
                "max_allowed": workspace.max_topics
            }
        )

    # Generate topics...
    topics = generate_ai_topics(workspace)

    return success(
        data={"topics": topics, "generated_count": len(topics)},
        request=request,
        message=f"Generated {len(topics)} topics successfully"
    )
```

### Frontend Integration

#### Updated Frontend Error Handling
```typescript
// Before: Complex error classification needed
if (error.response?.status === 422) {
  // Handle validation error
} else if (error.response?.status === 404) {
  // Handle not found
}

// After: Standardized error structure
const errorResponse: StandardApiResponse = await response.json();
if (!errorResponse.success) {
  const error = errorResponse.error;

  // All errors have consistent structure
  console.log("Error code:", error.code);
  console.log("Severity:", error.severity);
  console.log("Request ID:", errorResponse.meta.request_id);

  // Handle field-level validation errors
  if (error.details) {
    error.details.forEach(detail => {
      console.log(`Field ${detail.field}: ${detail.message}`);
    });
  }
}
```

## 🔧 Testing

### Running Integration Tests
```bash
# Activate virtual environment
cd wrext-backend
source .venv/bin/activate

# Install dependencies if needed
pip install fastapi pytest httpx

# Run integration tests
python test_middleware_integration.py
```

### Manual Testing with cURL
```bash
# Test success response
curl -H "X-Request-ID: test_123" http://localhost:8000/health

# Test error response
curl -X POST -H "Content-Type: application/json" \
  -d '{"email": "invalid-email"}' \
  http://localhost:8000/api/user/register
```

## 📊 Monitoring and Debugging

### Request Correlation
All requests include a unique `request_id` that appears in:
- Response metadata
- Log entries
- Error messages
- Response headers (`X-Request-ID`)

### Log Monitoring
```python
# Logs include structured data for monitoring
logger.info("Request completed", extra={
    "request_id": "req_123",
    "method": "POST",
    "path": "/api/users",
    "status_code": 201,
    "processing_time_ms": 150,
    "event_type": "request_success"
})
```

### Error Tracking
```python
# Errors include context for debugging
logger.error("Validation failed", extra={
    "request_id": "req_456",
    "error_code": "validation_failed",
    "status_code": 422,
    "field_errors": ["email", "password"],
    "event_type": "validation_error"
})
```

## 🔐 Security Features

### Sensitive Data Filtering
- Automatically filters sensitive fields from error details
- Truncates long values to prevent information leakage
- Excludes sensitive context in production mode

### Error Information Control
```python
# Development mode: Include debug information
ErrorHandlerMiddleware(include_debug_info=True)

# Production mode: Filter sensitive data
ErrorHandlerMiddleware(
    include_debug_info=False,
    filter_sensitive_data=True
)
```

## 📈 Performance Impact

### Middleware Overhead
- Request tracking: ~1-2ms per request
- Error handling: ~0.5ms per request
- Response formatting: ~0.1ms per request

### Benefits
- Consistent error handling reduces debugging time
- Request correlation improves troubleshooting
- Structured logging enables better monitoring
- Standardized responses simplify frontend integration

## 🎛 Configuration

### Environment Variables
```bash
# Server configuration
HOST=0.0.0.0
PORT=8000
DEBUG=false
ENVIRONMENT=production

# Database
POSTGRES_URI_CUSTOM=postgresql://user:pass@localhost/db

# Security
SECRET_KEY=your-secret-key
ALGORITHM=HS256
```

### FastAPI Application Setup
```python
from src.api.middleware import RequestTrackerMiddleware, ErrorHandlerMiddleware

app = FastAPI(title="Wrext API", version="1.0.0")

# Add middleware in correct order
app.add_middleware(RequestTrackerMiddleware)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(CORSMiddleware)

# Setup exception handlers
setup_exception_handlers(app)
```

## 🚧 Migration Guide

### From Old Response Format
```python
# Old format
return {"status": 200, "message": "Success", "data": result}

# New format
return success(
    data=result,
    request=request,
    message="Success"
)
```

### Error Handling Migration
```python
# Old format
raise HTTPException(status_code=404, detail="User not found")

# New format
raise ResourceNotFoundException(
    resource_type="user",
    resource_id=user_id
)
```

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://pydantic-docs.helpmanual.io/)
- [Python Logging Documentation](https://docs.python.org/3/library/logging.html)

## 🤝 Contributing

When adding new endpoints:
1. Use the response utilities (`success`, `error`, `created`, etc.)
2. Create specific exception classes for domain errors
3. Include proper request tracking with `Request` parameter
4. Add comprehensive error handling and logging
5. Update tests to verify response format

---

**✅ The consistent response and error handling system is now active across all API endpoints!**