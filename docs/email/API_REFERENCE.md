# Email System API Reference

**Last Updated:** 2025-10-12
**System:** WREXT Email Integration
**Version:** 1.0.0

---

## Table of Contents

1. [Overview](#overview)
2. [EmailService API](#emailservice-api)
3. [Webhook Endpoints](#webhook-endpoints)
4. [Preview API](#preview-api)
5. [Data Models](#data-models)
6. [Error Handling](#error-handling)
7. [Code Examples](#code-examples)

---

## Overview

The WREXT email system provides several API layers:

- **EmailService**: Python service class for sending emails (internal use)
- **Webhook API**: REST endpoints for receiving Resend webhook events
- **Preview API**: REST endpoints for previewing email templates
- **Provider Interface**: Abstract interface for email providers

### Base URL

```
Production: https://api.wrext.com/api/v1/email
Staging:    https://staging-api.wrext.com/api/v1/email
```

### Authentication

Most endpoints require JWT authentication via Bearer token:

```bash
Authorization: Bearer <your-jwt-token>
```

Webhook endpoints use Svix signature verification (no JWT required).

---

## EmailService API

### Class: `EmailService`

**Location:** `src/services/email_service.py`

The main service class for sending emails programmatically within the application.

#### Initialization

```python
from src.services.email_service import EmailService
from src.api.database.async_database import get_async_db

async for db in get_async_db():
    email_service = EmailService(db)
    break
```

#### Method: `send_email()`

Send an email with database logging and automatic retry.

**Signature:**
```python
async def send_email(
    self,
    to: str,
    subject: str,
    html: str,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    workspace_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    template_type: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    retry_on_failure: bool = True,
    auto_commit: bool = True
) -> EmailLog
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `to` | `str` | ✅ Yes | - | Recipient email address |
| `subject` | `str` | ✅ Yes | - | Email subject line |
| `html` | `str` | ✅ Yes | - | HTML email content |
| `from_email` | `str` | No | Config value | Sender email address |
| `from_name` | `str` | No | Config value | Sender display name |
| `cc` | `List[str]` | No | `None` | CC recipients |
| `bcc` | `List[str]` | No | `None` | BCC recipients |
| `reply_to` | `str` | No | `None` | Reply-to address |
| `workspace_id` | `UUID` | No | `None` | Associated workspace ID |
| `user_id` | `UUID` | No | `None` | Associated user ID |
| `template_type` | `str` | No | `None` | Template identifier |
| `tags` | `Dict[str, str]` | No | `None` | Custom tags for filtering |
| `retry_on_failure` | `bool` | No | `True` | Enable fallback provider |
| `auto_commit` | `bool` | No | `True` | Auto-commit transaction |

**Returns:**
- `EmailLog`: Database record with send status

**Raises:**
- `Exception`: If `email_enabled=False` or email system is disabled

**Example:**
```python
from src.services.email_service import EmailService
from emails.templates.auth import create_verification_email

async def send_verification_email(user_email: str, user_name: str, token: str, db):
    """Send email verification to new user."""

    # Generate email HTML
    html = create_verification_email(
        user_name=user_name,
        verification_token=token,
        frontend_url="https://app.wrext.com"
    )

    # Send email
    email_service = EmailService(db)
    email_log = await email_service.send_email(
        to=user_email,
        subject="Verify Your Email - WREXT",
        html=html,
        template_type="email_verification",
        tags={"type": "auth", "action": "verify"}
    )

    return email_log
```

#### Method: `get_email_log()`

Retrieve email log by ID.

**Signature:**
```python
async def get_email_log(self, email_log_id: UUID) -> Optional[EmailLog]
```

**Parameters:**
- `email_log_id` (UUID): Email log UUID

**Returns:**
- `EmailLog | None`: Email log record or None if not found

**Example:**
```python
email_log = await email_service.get_email_log(email_log_id)
if email_log:
    print(f"Status: {email_log.status}")
    print(f"Sent at: {email_log.sent_at}")
```

#### Method: `get_emails_for_user()`

Get all emails sent to a specific user.

**Signature:**
```python
async def get_emails_for_user(
    self,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0
) -> List[EmailLog]
```

**Parameters:**
- `user_id` (UUID): User UUID
- `limit` (int): Maximum records to return (default: 50)
- `offset` (int): Pagination offset (default: 0)

**Returns:**
- `List[EmailLog]`: List of email logs

**Example:**
```python
user_emails = await email_service.get_emails_for_user(
    user_id=user_id,
    limit=20
)

for email in user_emails:
    print(f"{email.subject} - {email.status}")
```

#### Method: `get_emails_for_workspace()`

Get all emails for a workspace.

**Signature:**
```python
async def get_emails_for_workspace(
    self,
    workspace_id: UUID,
    limit: int = 50,
    offset: int = 0
) -> List[EmailLog]
```

**Parameters:**
- `workspace_id` (UUID): Workspace UUID
- `limit` (int): Maximum records (default: 50)
- `offset` (int): Pagination offset (default: 0)

**Returns:**
- `List[EmailLog]`: List of email logs

#### Method: `get_recent_failures()`

Get recent failed emails for debugging.

**Signature:**
```python
async def get_recent_failures(
    self,
    hours: int = 24,
    limit: int = 100
) -> List[EmailLog]
```

**Parameters:**
- `hours` (int): Time window in hours (default: 24)
- `limit` (int): Maximum records (default: 100)

**Returns:**
- `List[EmailLog]`: List of failed email logs

**Example:**
```python
# Get emails that failed in last 6 hours
failed = await email_service.get_recent_failures(hours=6)

for email in failed:
    print(f"Failed: {email.to_email}")
    print(f"Error: {email.error_message}")
```

#### Method: `retry_failed_email()`

Retry sending a failed email.

**Signature:**
```python
async def retry_failed_email(
    self,
    email_log_id: UUID,
    auto_commit: bool = True
) -> EmailLog
```

**Parameters:**
- `email_log_id` (UUID): Email log UUID to retry
- `auto_commit` (bool): Auto-commit transaction (default: True)

**Returns:**
- `EmailLog`: Updated email log with new send status

**Raises:**
- `ValueError`: If email log not found or status is not 'failed'

**Example:**
```python
# Retry specific failed email
retried = await email_service.retry_failed_email(failed_email_id)

if retried.status == "sent":
    print("Retry successful!")
else:
    print(f"Retry failed: {retried.error_message}")
```

---

## Webhook Endpoints

### POST `/api/v1/email/webhooks/resend`

Receive and process webhook events from Resend.

**Authentication:** Svix signature verification (no JWT required)

**Headers Required:**
```
Content-Type: application/json
svix-id: <message-id>
svix-timestamp: <unix-timestamp>
svix-signature: <signature>
```

**Request Body:**
```json
{
  "type": "email.delivered",
  "created_at": "2025-10-12T12:00:00Z",
  "data": {
    "email_id": "msg_abc123",
    "to": "user@example.com",
    "subject": "Welcome to WREXT",
    "from": "WREXT <noreply@wrext.com>"
  }
}
```

**Supported Event Types:**

| Event Type | Description |
|------------|-------------|
| `email.sent` | Email accepted by Resend |
| `email.delivered` | Email delivered to recipient |
| `email.delivery_delayed` | Temporary delivery failure |
| `email.bounced` | Permanent delivery failure |
| `email.complained` | Recipient marked as spam |
| `email.opened` | Recipient opened email |
| `email.clicked` | Recipient clicked link |

**Response:**
```json
{
  "status": "ok",
  "message": "Webhook received and queued for processing"
}
```

**Status Codes:**
- `200 OK`: Webhook received and queued
- `401 Unauthorized`: Invalid signature
- `400 Bad Request`: Malformed JSON
- `500 Internal Server Error`: Processing error

**Example cURL:**
```bash
# This is typically called by Resend, not manually
curl -X POST https://api.wrext.com/api/v1/email/webhooks/resend \
  -H "Content-Type: application/json" \
  -H "svix-id: msg_xyz" \
  -H "svix-timestamp: 1697040000" \
  -H "svix-signature: v1,sig..." \
  -d '{
    "type": "email.delivered",
    "created_at": "2025-10-12T12:00:00Z",
    "data": {
      "email_id": "msg_abc123",
      "to": "user@example.com"
    }
  }'
```

**Webhook Configuration:**

Add this endpoint to your Resend dashboard:
1. Go to https://resend.com/webhooks
2. Click "Add Endpoint"
3. URL: `https://your-domain.com/api/v1/email/webhooks/resend`
4. Events: Select all email events
5. Copy the signing secret → `RESEND_WEBHOOK_SECRET`

### GET `/api/v1/email/webhooks/health`

Health check for webhook service.

**Authentication:** None required

**Response:**
```json
{
  "status": "healthy",
  "service": "resend-webhooks",
  "webhook_secret_configured": true
}
```

**Status Codes:**
- `200 OK`: Service is healthy

---

## Preview API

### POST `/api/v1/email/preview/auth`

Preview authentication email templates.

**Authentication:** JWT required

**Request Body:**
```json
{
  "template_type": "verification",
  "user_name": "John Doe",
  "user_email": "john@example.com",
  "token": "abc123def456",
  "frontend_url": "https://app.wrext.com"
}
```

**Template Types:**
- `verification`: Email verification
- `password_reset`: Password reset
- `welcome`: Welcome email

**Response:**
```json
{
  "html": "<html>...</html>",
  "template_type": "verification",
  "subject": "Verify Your Email Address - WREXT",
  "preview_text": "Click the link below to verify your email",
  "metadata": {
    "template_name": "Auth - Verification",
    "size_bytes": 5432,
    "frontend_url": "https://app.wrext.com"
  }
}
```

**Status Codes:**
- `200 OK`: Preview generated
- `400 Bad Request`: Invalid template type
- `401 Unauthorized`: Missing/invalid JWT
- `500 Internal Server Error`: Template rendering error

**Example:**
```bash
curl -X POST https://api.wrext.com/api/v1/email/preview/auth \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_type": "verification",
    "user_name": "Test User",
    "token": "test-token-123",
    "frontend_url": "https://app.wrext.com"
  }'
```

### POST `/api/v1/email/preview/workspace`

Preview workspace email templates.

**Authentication:** JWT required

**Request Body:**
```json
{
  "template_type": "invitation",
  "workspace_name": "Acme Corp",
  "workspace_id": "workspace-uuid",
  "user_name": "John Doe",
  "role_name": "Editor",
  "invitation_token": "inv_abc123",
  "expiry_days": 7,
  "workspace_description": "Marketing team workspace",
  "frontend_url": "https://app.wrext.com"
}
```

**Template Types:**
- `invitation`: Workspace invitation
- `invitation_accepted`: New member joined notification
- `role_changed`: Role update notification
- `member_removed`: Member removed notification

**Response:**
```json
{
  "html": "<html>...</html>",
  "template_type": "invitation",
  "subject": "You've been invited to join Acme Corp",
  "preview_text": "John Doe has invited you to join Acme Corp",
  "metadata": {
    "template_name": "Workspace - Invitation",
    "size_bytes": 6891,
    "workspace_name": "Acme Corp",
    "frontend_url": "https://app.wrext.com"
  }
}
```

### POST `/api/v1/email/preview/auth/html`

Preview auth email as raw HTML (for rendering in iframe).

**Authentication:** JWT required

**Request Body:** Same as `/preview/auth`

**Response:** Raw HTML (Content-Type: text/html)

**Example:**
```html
<!-- Render preview in iframe -->
<iframe
  id="email-preview"
  src="/api/v1/email/preview/auth/html"
  style="width: 600px; height: 800px; border: 1px solid #ccc;">
</iframe>
```

### POST `/api/v1/email/preview/workspace/html`

Preview workspace email as raw HTML.

**Authentication:** JWT required

**Request Body:** Same as `/preview/workspace`

**Response:** Raw HTML (Content-Type: text/html)

---

## Data Models

### EmailLog

Database model for email send records.

**Table:** `email_logs`

**Schema:**
```python
{
  "id": UUID,                      # Primary key
  "workspace_id": UUID | None,     # Associated workspace
  "user_id": UUID | None,          # Associated user
  "provider": str,                 # Provider used (resend/smtp/mock)
  "provider_message_id": str | None, # Provider's message ID
  "to_email": str,                 # Recipient address
  "from_email": str,               # Sender address
  "subject": str,                  # Email subject
  "template_type": str | None,     # Template identifier
  "status": str,                   # queued/sent/delivered/bounced/failed/complained
  "tags": dict | None,             # Custom tags
  "error_message": str | None,     # Error details if failed
  "provider_response": dict | None, # Full provider response
  "created_at": datetime,          # When email was created
  "sent_at": datetime | None,      # When email was sent
  "delivered_at": datetime | None, # When email was delivered
  "failed_at": datetime | None     # When email failed
}
```

**Status Values:**
- `queued`: Email queued for sending
- `sent`: Email accepted by provider
- `delivered`: Email delivered to recipient
- `bounced`: Email bounced (permanent failure)
- `failed`: Email send failed (temporary or permanent)
- `complained`: Recipient marked as spam

### EmailEvent

Database model for webhook events.

**Table:** `email_events`

**Schema:**
```python
{
  "id": UUID,                      # Primary key
  "email_log_id": UUID | None,     # Linked email log
  "provider": str,                 # Event source (resend)
  "provider_event_id": str,        # Unique event ID (for deduplication)
  "provider_message_id": str,      # Provider's message ID
  "event_type": str,               # Event type (email.delivered, etc)
  "event_data": dict,              # Full event payload
  "created_at": datetime           # When event was received
}
```

**Event Types:**
- `email.sent`
- `email.delivered`
- `email.delivery_delayed`
- `email.bounced`
- `email.complained`
- `email.opened`
- `email.clicked`

### EmailMessage

Data class for composing emails.

**Location:** `src/providers/email/base.py`

```python
@dataclass
class EmailMessage:
    to: List[EmailRecipient]          # Recipients
    subject: str                       # Subject line
    html: str                          # HTML content
    from_email: str                    # Sender email
    from_name: Optional[str] = None    # Sender name
    reply_to: Optional[str] = None     # Reply-to address
    cc: Optional[List[EmailRecipient]] = None  # CC recipients
    bcc: Optional[List[EmailRecipient]] = None # BCC recipients
    tags: Optional[Dict[str, str]] = None # Custom tags
```

### EmailRecipient

Data class for email recipients.

```python
@dataclass
class EmailRecipient:
    email: str                # Email address
    name: Optional[str] = None # Display name
```

### EmailResult

Data class for send results.

```python
@dataclass
class EmailResult:
    success: bool                          # Send success/failure
    message_id: Optional[str] = None       # Provider message ID
    error: Optional[str] = None            # Error message if failed
    provider_response: Optional[Dict] = None # Full provider response
```

---

## Error Handling

### Common Error Responses

#### 401 Unauthorized
```json
{
  "detail": "Invalid webhook signature"
}
```

**Cause:** Webhook signature verification failed

**Fix:** Verify `RESEND_WEBHOOK_SECRET` matches Resend dashboard

#### 400 Bad Request
```json
{
  "detail": "Invalid JSON payload"
}
```

**Cause:** Malformed request body

**Fix:** Ensure valid JSON with correct structure

#### 500 Internal Server Error
```json
{
  "detail": "Internal server error processing webhook"
}
```

**Cause:** Unexpected server error

**Fix:** Check application logs for details

### Exception Handling in EmailService

```python
try:
    email_log = await email_service.send_email(
        to="user@example.com",
        subject="Test",
        html="<p>Test</p>"
    )

    if email_log.status == "sent":
        print("Email sent successfully")
    else:
        print(f"Email failed: {email_log.error_message}")

except Exception as e:
    # Email system disabled or database error
    logger.error(f"Failed to send email: {e}")
    # Handle gracefully - don't block user flow
```

---

## Code Examples

### Example 1: Send Verification Email

```python
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.async_database import get_async_db
from src.services.email_service import EmailService
from emails.templates.auth import create_verification_email

router = APIRouter()

@router.post("/auth/register")
async def register_user(
    user_data: UserRegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    # Create user in database
    user = await create_user(user_data, db)

    # Generate verification token
    token = generate_verification_token(user.id)

    # Send verification email in background
    background_tasks.add_task(
        send_verification_email,
        user.email,
        user.name,
        token,
        db
    )

    return {"message": "User registered. Check email for verification link."}

async def send_verification_email(
    email: str,
    name: str,
    token: str,
    db: AsyncSession
):
    """Send verification email in background."""
    try:
        # Generate email HTML
        html = create_verification_email(
            user_name=name,
            verification_token=token,
            frontend_url="https://app.wrext.com"
        )

        # Send email
        email_service = EmailService(db)
        await email_service.send_email(
            to=email,
            subject="Verify Your Email - WREXT",
            html=html,
            template_type="email_verification",
            tags={"type": "auth", "action": "verify"}
        )

        logger.info(f"Verification email sent to {email}")

    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")
        # Don't fail user registration if email fails
```

### Example 2: Send Workspace Invitation

```python
from src.services.email_service import EmailService
from emails.templates.workspace import create_workspace_invitation_email

async def send_workspace_invitation(
    workspace_id: UUID,
    workspace_name: str,
    inviter_name: str,
    invitee_email: str,
    role_name: str,
    invitation_token: str,
    db: AsyncSession
):
    """Send workspace invitation email."""

    # Generate email HTML
    html = create_workspace_invitation_email(
        workspace_name=workspace_name,
        inviter_name=inviter_name,
        invitation_token=invitation_token,
        role_name=role_name,
        expiry_days=7,
        workspace_description="Collaborate on content creation",
        frontend_url="https://app.wrext.com"
    )

    # Send email
    email_service = EmailService(db)
    email_log = await email_service.send_email(
        to=invitee_email,
        subject=f"You've been invited to join {workspace_name}",
        html=html,
        workspace_id=workspace_id,
        template_type="workspace_invitation",
        tags={
            "type": "workspace",
            "action": "invite",
            "workspace": workspace_name
        }
    )

    return email_log
```

### Example 3: Query Email Status

```python
async def check_email_delivery_status(
    email_log_id: UUID,
    db: AsyncSession
):
    """Check if email was delivered and opened."""

    email_service = EmailService(db)
    email_log = await email_service.get_email_log(email_log_id)

    if not email_log:
        return {"error": "Email not found"}

    # Get related events
    from src.services.email_event_service import EmailEventService
    event_service = EmailEventService(db)
    events = await event_service.get_events_for_email_log(email_log_id)

    return {
        "email_id": str(email_log.id),
        "to": email_log.to_email,
        "status": email_log.status,
        "sent_at": email_log.sent_at,
        "delivered_at": email_log.delivered_at,
        "events": [
            {
                "type": event.event_type,
                "timestamp": event.created_at
            }
            for event in events
        ],
        "opened": any(e.event_type == "email.opened" for e in events),
        "clicked": any(e.event_type == "email.clicked" for e in events)
    }
```

### Example 4: Bulk Email Status Check

```python
async def get_workspace_email_stats(
    workspace_id: UUID,
    db: AsyncSession
):
    """Get email statistics for a workspace."""

    email_service = EmailService(db)
    emails = await email_service.get_emails_for_workspace(
        workspace_id=workspace_id,
        limit=1000
    )

    total = len(emails)
    delivered = sum(1 for e in emails if e.status == "delivered")
    failed = sum(1 for e in emails if e.status == "failed")
    bounced = sum(1 for e in emails if e.status == "bounced")

    return {
        "workspace_id": str(workspace_id),
        "total_emails": total,
        "delivered": delivered,
        "failed": failed,
        "bounced": bounced,
        "delivery_rate": (delivered / total * 100) if total > 0 else 0
    }
```

### Example 5: Retry Failed Emails

```python
async def retry_all_recent_failures(db: AsyncSession):
    """Retry all emails that failed in the last hour."""

    email_service = EmailService(db)

    # Get recent failures
    failed_emails = await email_service.get_recent_failures(
        hours=1,
        limit=50
    )

    results = []
    for email in failed_emails:
        try:
            retried = await email_service.retry_failed_email(email.id)
            results.append({
                "email_id": str(email.id),
                "to": email.to_email,
                "retry_status": retried.status,
                "success": retried.status == "sent"
            })
        except Exception as e:
            results.append({
                "email_id": str(email.id),
                "to": email.to_email,
                "retry_status": "error",
                "error": str(e),
                "success": False
            })

    return {
        "total_retried": len(results),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results
    }
```

---

## Integration Guide

### Using EmailService in Routes

```python
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.async_database import get_async_db
from src.services.email_service import EmailService

router = APIRouter()

@router.post("/send-custom-email")
async def send_custom_email(
    request: CustomEmailRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    """Send custom email."""

    # Queue email in background
    background_tasks.add_task(
        _send_email_task,
        request.to,
        request.subject,
        request.html,
        db
    )

    return {"message": "Email queued"}

async def _send_email_task(
    to: str,
    subject: str,
    html: str,
    db: AsyncSession
):
    """Background task to send email."""
    email_service = EmailService(db)

    await email_service.send_email(
        to=to,
        subject=subject,
        html=html
    )
```

### Provider Switching

```python
# Switch providers via environment variable
# No code changes needed!

# Use Resend (default)
EMAIL_PROVIDER=resend

# Switch to SMTP
EMAIL_PROVIDER=smtp

# Use mock for testing
EMAIL_PROVIDER=mock
```

---

## Rate Limits

### Resend Rate Limits

- **Free tier:** 100 emails/day, 3,000/month
- **Pro tier:** No daily limit, 50,000/month included
- **API calls:** 10 requests/second

### Application Rate Limits

No rate limits enforced at application level. Relies on Resend's limits.

---

## Support

- **Documentation:** [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)
- **Operations:** [OPERATIONS_RUNBOOK.md](./OPERATIONS_RUNBOOK.md)
- **Resend API Docs:** https://resend.com/docs/api-reference/introduction
- **Support:** Create issue in repository
