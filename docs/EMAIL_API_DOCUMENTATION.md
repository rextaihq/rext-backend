# Email System API Documentation

**Version**: 1.0
**Last Updated**: October 12, 2025
**Status**: Production Ready

---

## Overview

The Wrext Email System provides a comprehensive API for managing email notifications and user preferences. This documentation covers all email-related endpoints and helper functions.

---

## Table of Contents

1. [Email Helpers API](#email-helpers-api)
2. [Email Preferences API](#email-preferences-api)
3. [Email Types](#email-types)
4. [Error Handling](#error-handling)
5. [Examples](#examples)

---

## Email Helpers API

### `send_auth_email()`

Send authentication emails using professional templates.

**Module**: `src.services.email_helpers`

**Function Signature**:
```python
async def send_auth_email(
    db: AsyncSession,
    email_type: Literal["verification", "password_reset", "welcome"],
    recipient_email: str,
    user_name: str,
    user_id: UUID,
    token: str = None,
    frontend_url: str = None,
    background_tasks: BackgroundTasks = None,
    **kwargs
) -> bool
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `db` | AsyncSession | Yes | Database session |
| `email_type` | str | Yes | Type of auth email: "verification", "password_reset", "welcome" |
| `recipient_email` | str | Yes | Recipient's email address |
| `user_name` | str | Yes | User's name for personalization |
| `user_id` | UUID | Yes | User ID for logging |
| `token` | str | No | Verification or reset token (required for verification/reset) |
| `frontend_url` | str | No | Frontend URL for links (defaults to env variable) |
| `background_tasks` | BackgroundTasks | No | FastAPI background tasks for async sending |

**Returns**: `bool` - True if email sent successfully, False otherwise

**Example**:
```python
from src.services.email_helpers import send_auth_email

# Send verification email
success = await send_auth_email(
    db=db,
    email_type="verification",
    recipient_email="user@example.com",
    user_name="John Doe",
    user_id=user.id,
    token="verify_abc123",
    frontend_url="https://app.wrext.com",
    background_tasks=background_tasks
)
```

---

### `send_workspace_email()`

Send workspace emails with DB template support and preference checking.

**Module**: `src.services.email_helpers`

**Function Signature**:
```python
async def send_workspace_email(
    db: AsyncSession,
    email_type: Literal["invitation", "invitation_accepted", "role_changed", "member_removed"],
    workspace_id: UUID,
    recipient_email: str,
    user_id: UUID = None,
    background_tasks: BackgroundTasks = None,
    **context
) -> bool
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `db` | AsyncSession | Yes | Database session |
| `email_type` | str | Yes | Type of workspace email |
| `workspace_id` | UUID | Yes | Workspace ID |
| `recipient_email` | str | Yes | Recipient's email address |
| `user_id` | UUID | No | User ID for preferences check |
| `background_tasks` | BackgroundTasks | No | FastAPI background tasks |
| `**context` | dict | No | Template-specific context variables |

**Context Variables by Email Type**:

**invitation**:
- `workspace_name` (str)
- `inviter_name` (str)
- `role_name` (str)
- `invitation_token` (str)
- `expiry_days` (int)
- `frontend_url` (str)

**invitation_accepted**:
- `workspace_name` (str)
- `new_member_name` (str)
- `new_member_email` (str)
- `role_name` (str)
- `frontend_url` (str)

**role_changed**:
- `workspace_name` (str)
- `member_name` (str)
- `old_role_name` (str)
- `new_role_name` (str)
- `changed_by_name` (str)
- `frontend_url` (str)

**member_removed**:
- `workspace_name` (str)
- `member_name` (str)
- `removed_by_name` (str)
- `reason` (str, optional)
- `frontend_url` (str)

**Returns**: `bool` - True if email sent successfully, False if blocked by preferences or failed

**Example**:
```python
from src.services.email_helpers import send_workspace_email

# Send invitation email
success = await send_workspace_email(
    db=db,
    email_type="invitation",
    workspace_id=workspace.id,
    recipient_email="invitee@example.com",
    workspace_name="Acme Inc",
    inviter_name="Admin User",
    role_name="Editor",
    invitation_token="inv_xyz789",
    expiry_days=7,
    frontend_url="https://app.wrext.com",
    background_tasks=background_tasks
)
```

---

## Email Preferences API

### GET `/api/v1/user/email-preferences/`

Get user's email preferences.

**Authentication**: Required

**Response**:
```json
{
  "data": {
    "id": "ep_abc123",
    "user_id": "user_456",
    "workspace_invitation": true,
    "invitation_accepted": true,
    "role_changed": true,
    "member_removed": true,
    "marketing": false,
    "unsubscribe_token": "token_xyz",
    "created_at": "2025-10-12T10:00:00",
    "updated_at": "2025-10-12T10:00:00"
  },
  "message": "Email preferences retrieved successfully"
}
```

**Example**:
```bash
curl -X GET "https://api.wrext.com/api/v1/user/email-preferences/" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### PUT `/api/v1/user/email-preferences/`

Update user's email preferences.

**Authentication**: Required

**Request Body**:
```json
{
  "workspace_invitation": false,
  "invitation_accepted": true,
  "role_changed": true,
  "member_removed": false,
  "marketing": false
}
```

**Response**:
```json
{
  "data": {
    "id": "ep_abc123",
    "user_id": "user_456",
    "workspace_invitation": false,
    "invitation_accepted": true,
    "role_changed": true,
    "member_removed": false,
    "marketing": false,
    "unsubscribe_token": "token_xyz",
    "created_at": "2025-10-12T10:00:00",
    "updated_at": "2025-10-12T12:00:00"
  },
  "message": "Email preferences updated successfully"
}
```

**Example**:
```bash
curl -X PUT "https://api.wrext.com/api/v1/user/email-preferences/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_invitation": false,
    "marketing": false
  }'
```

---

### POST `/api/v1/user/email-preferences/unsubscribe`

Unsubscribe from emails using token (no authentication required).

**Authentication**: Not Required (uses token from email link)

**Request Body**:
```json
{
  "token": "unsubscribe_token_from_email",
  "email_types": ["workspace_invitation", "role_changed"]
}
```

**Response**:
```json
{
  "data": {
    "unsubscribed_from": "workspace_invitation, role_changed"
  },
  "message": "Successfully unsubscribed from workspace_invitation, role_changed"
}
```

**Unsubscribe from All Emails**:
```json
{
  "token": "unsubscribe_token_from_email",
  "email_types": []
}
```

**Example**:
```bash
curl -X POST "https://api.wrext.com/api/v1/user/email-preferences/unsubscribe" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "abc123xyz",
    "email_types": []
  }'
```

---

## Email Types

### Authentication Emails

| Type | Template | Trigger | Customizable |
|------|----------|---------|--------------|
| `verification` | Python | User registration | No |
| `password_reset` | Python | Forgot password | No |
| `welcome` | Python | Email verified | No |

### Workspace Emails

| Type | Template | Trigger | Customizable | Preferences Check |
|------|----------|---------|--------------|-------------------|
| `invitation` | DB/Python | Member invited | Per workspace | No (guest user) |
| `invitation_accepted` | Python | Invitation accepted | No | Yes |
| `role_changed` | Python | Member role updated | No | Yes |
| `member_removed` | Python | Member removed | No | Yes |

---

## Error Handling

### Email Helper Errors

Both `send_auth_email()` and `send_workspace_email()` return `False` on errors and log the exception. They never raise exceptions to avoid blocking requests.

**Example Error Handling**:
```python
success = await send_auth_email(...)
if not success:
    logger.warning(f"Failed to send email to {recipient_email}")
    # Continue with request - email failure shouldn't block user action
```

### API Errors

Email Preferences API endpoints return standard HTTP error codes:

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Invalid request body |
| 401 | Unauthorized (missing/invalid token) |
| 404 | Resource not found (invalid unsubscribe token) |
| 500 | Internal server error |

---

## Examples

### Complete User Registration Flow

```python
from fastapi import APIRouter, BackgroundTasks, Depends
from src.services.email_helpers import send_auth_email

@router.post("/register")
async def register_user(
    user_data: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    # Create user
    new_user = await auth_service.register_user(...)

    # Send verification email in background
    await send_auth_email(
        db=db,
        email_type="verification",
        recipient_email=new_user.email,
        user_name=new_user.first_name,
        user_id=new_user.id,
        token=verification_token,
        frontend_url=os.getenv("FRONTEND_URL"),
        background_tasks=background_tasks
    )

    return {"message": "User created, verification email sent"}
```

### Complete Workspace Invitation Flow

```python
from src.services.email_helpers import send_workspace_email

@router.post("/workspace/{workspace_id}/invite")
async def invite_member(
    workspace_id: str,
    invitation_data: InvitationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    # Create invitation
    invitation = await service.create_invitation(...)

    # Send invitation email
    await send_workspace_email(
        db=db,
        email_type="invitation",
        workspace_id=UUID(workspace_id),
        recipient_email=invitation_data.email,
        workspace_name=workspace.name,
        inviter_name=current_user.first_name,
        role_name=role.display_name,
        invitation_token=invitation.token,
        expiry_days=7,
        frontend_url=os.getenv("FRONTEND_URL"),
        background_tasks=background_tasks
    )

    return {"message": "Invitation sent"}
```

### Check Email Preferences Before Sending

```python
from src.services.email_preferences_service import EmailPreferencesService

# Automatic check (recommended)
success = await send_workspace_email(
    db=db,
    email_type="role_changed",
    workspace_id=workspace.id,
    recipient_email=member.email,
    user_id=member.user_id,  # Triggers automatic preferences check
    workspace_name=workspace.name,
    ...
)

# Manual check (if needed)
prefs_service = EmailPreferencesService(db)
can_send = await prefs_service.check_can_send(
    user_id=member.user_id,
    email_type="role_changed",
    db=db
)

if can_send:
    await send_workspace_email(...)
```

---

## Best Practices

### 1. Always Use Background Tasks for Production

```python
# ✅ GOOD - Non-blocking
await send_auth_email(
    ...,
    background_tasks=background_tasks
)

# ❌ BAD - Blocks request until email sent
await send_auth_email(
    ...,
    background_tasks=None
)
```

### 2. Always Provide user_id for Workspace Emails

```python
# ✅ GOOD - Respects user preferences
await send_workspace_email(
    ...,
    user_id=member.user_id  # Enables preference check
)

# ⚠️ ACCEPTABLE - For guest users (invitations)
await send_workspace_email(
    email_type="invitation",
    ...
    # No user_id - guest doesn't have account yet
)
```

### 3. Handle Email Failures Gracefully

```python
# ✅ GOOD - Email failure doesn't block user action
success = await send_auth_email(...)
if not success:
    logger.warning("Email failed but user created successfully")

# ❌ BAD - Don't raise exceptions for email failures
if not await send_auth_email(...):
    raise Exception("Email failed")  # Don't do this
```

### 4. Use Appropriate Email Types

```python
# ✅ GOOD - Use correct email type
await send_auth_email(email_type="verification", ...)
await send_workspace_email(email_type="invitation", ...)

# ❌ BAD - Don't use wrong type
await send_auth_email(email_type="invitation", ...)  # Wrong!
```

---

## Rate Limiting

Email sending is not currently rate-limited at the helper level. Rate limiting should be applied at the route level using the existing rate limiting middleware.

---

## Monitoring & Logging

All emails are logged to the `email_logs` table with the following information:
- Email ID
- Recipient
- Subject
- Status (queued, sent, delivered, failed, bounced)
- Provider used
- Timestamps
- Error messages (if failed)

**Query Recent Emails**:
```sql
SELECT * FROM email_logs
WHERE created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;
```

**Check Email Status**:
```sql
SELECT status, COUNT(*)
FROM email_logs
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY status;
```

---

## Support

For issues or questions:
- **Documentation**: `/docs/EMAIL_DEVELOPER_GUIDE.md`
- **Code**: `src/services/email_helpers.py`
- **Tests**: `tests/unit/services/test_email_helpers.py`

---

**Last Updated**: October 12, 2025
**Maintainer**: Wrext Backend Team
