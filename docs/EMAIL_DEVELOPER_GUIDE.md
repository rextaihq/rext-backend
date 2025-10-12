# Email System Developer Guide

**Version**: 1.0
**Audience**: Backend Developers
**Last Updated**: October 12, 2025

---

## Table of Contents

1. [Introduction](#introduction)
2. [Architecture Overview](#architecture-overview)
3. [Adding a New Email Type](#adding-a-new-email-type)
4. [Modifying Existing Templates](#modifying-existing-templates)
5. [Testing Email Flows](#testing-email-flows)
6. [Troubleshooting](#troubleshooting)
7. [Advanced Topics](#advanced-topics)

---

## Introduction

This guide helps developers work with the Wrext email system. Whether you're adding new email types, modifying templates, or debugging issues, this document provides step-by-step instructions.

### Prerequisites

- Familiarity with FastAPI and async Python
- Understanding of SQLAlchemy ORM
- Basic knowledge of HTML/CSS for templates

---

## Architecture Overview

### System Components

```
┌─────────────────┐
│  Route Handler  │  (FastAPI endpoint)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Email Helper   │  (send_auth_email / send_workspace_email)
└────────┬────────┘
         │
         ├──────────────┐
         ▼              ▼
┌──────────────┐  ┌──────────────┐
│  Preferences │  │   Template   │
│    Service   │  │   Renderer   │
└──────┬───────┘  └──────┬───────┘
       │                 │
       └────────┬────────┘
                ▼
      ┌──────────────────┐
      │  Email Service   │
      └────────┬──────────┘
               │
               ▼
      ┌──────────────────┐
      │  Email Provider  │  (Resend/SMTP)
      └──────────────────┘
```

### File Structure

```
wrext-backend/
├── src/
│   ├── services/
│   │   ├── email_service.py          # Core email sending
│   │   ├── email_helpers.py          # High-level helpers (USE THIS)
│   │   └── email_preferences_service.py
│   ├── api/
│   │   ├── routes/
│   │   │   ├── users/
│   │   │   │   ├── auth.py           # Auth emails
│   │   │   │   └── email_preferences.py
│   │   │   └── workspaces/
│   │   │       └── workspace_members.py  # Workspace emails
│   │   └── models/
│   │       └── user_models/
│   │           └── email_preferences.py
│   └── providers/
│       └── email/
│           ├── resend_provider.py
│           └── mock_provider.py
├── emails/
│   ├── templates/
│   │   ├── auth/                     # Python templates
│   │   │   ├── verification.py
│   │   │   ├── password_reset.py
│   │   │   └── welcome.py
│   │   └── workspace/
│   │       ├── invitation.py
│   │       ├── invitation_accepted.py
│   │       ├── role_changed.py
│   │       └── member_removed.py
│   └── components/
│       ├── header.py
│       ├── footer.py
│       └── button.py
└── tests/
    ├── unit/services/
    │   ├── test_email_helpers.py
    │   └── test_email_preferences_service.py
    └── integration/
        └── test_email_flows.py
```

---

## Adding a New Email Type

### Step 1: Create Python Template

Create a new template file in `emails/templates/`:

**File**: `emails/templates/workspace/project_created.py`

```python
"""
Project Created Notification Template

Sent to workspace members when a new project is created.
"""
from emails.components import simple_header, primary_button, simple_footer
from emails.utils.renderer import compose_email


def create_project_created_email(
    workspace_name: str,
    project_name: str,
    created_by_name: str,
    project_url: str,
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """
    Render project created notification email.

    Args:
        workspace_name: Name of the workspace
        project_name: Name of the new project
        created_by_name: Name of person who created project
        project_url: Direct link to the project
        frontend_url: Base frontend URL

    Returns:
        Complete HTML email string
    """
    email_html = compose_email([
        simple_header(workspace_name),
        f"""
        <h1 style="color: #111827; font-size: 28px; font-weight: 700;">
            New Project: {project_name} 🎉
        </h1>
        """,
        f"""
        <p style="color: #374151; font-size: 16px; line-height: 24px;">
            <strong>{created_by_name}</strong> created a new project
            <strong>{project_name}</strong> in {workspace_name}.
        </p>
        """,
        primary_button("View Project", project_url),
        simple_footer()
    ], preview_text=f"New project: {project_name}")

    return email_html
```

### Step 2: Add to Email Helpers

Update `src/services/email_helpers.py`:

```python
# Add to Literal type hint
async def send_workspace_email(
    db: AsyncSession,
    email_type: Literal[
        "invitation",
        "invitation_accepted",
        "role_changed",
        "member_removed",
        "project_created"  # ADD THIS
    ],
    workspace_id: UUID,
    recipient_email: str,
    user_id: UUID = None,
    background_tasks: BackgroundTasks = None,
    **context
) -> bool:
    """..."""
    try:
        # ... existing code ...

        # Add to fallback logic
        from emails.templates.workspace import (
            # ... existing imports ...
            create_project_created_email  # ADD THIS
        )

        # ... existing code ...

        elif email_type == "project_created":  # ADD THIS
            html = create_project_created_email(**context)
            subject = f"New project created in {context.get('workspace_name')}"

        # ... rest of code ...
```

### Step 3: Add to Email Preferences (if needed)

If users should be able to opt-out of this email, add a preference:

**File**: `src/api/models/user_models/email_preferences.py`

```python
class EmailPreferences(Base):
    # ... existing fields ...
    project_created = Column(Boolean, default=True, nullable=False)  # ADD THIS
```

Create migration:
```bash
alembic revision -m "add_project_created_preference"
```

Update migration file:
```python
def upgrade():
    op.add_column('email_preferences',
        sa.Column('project_created', sa.Boolean(),
                  nullable=False, server_default='true'))

def downgrade():
    op.drop_column('email_preferences', 'project_created')
```

Run migration:
```bash
alembic upgrade head
```

### Step 4: Update EmailPreferencesService

Add to type mapping in `src/services/email_preferences_service.py`:

```python
async def check_can_send(self, user_id: UUID, email_type: str, db: AsyncSession) -> bool:
    """..."""
    prefs = await self.get_or_create_preferences(user_id, db)

    type_mapping = {
        # ... existing mappings ...
        "project_created": prefs.project_created,  # ADD THIS
    }

    return type_mapping.get(email_type, True)
```

### Step 5: Use in Route

**File**: `src/api/routes/workspaces/projects.py`

```python
from src.services.email_helpers import send_workspace_email

@router.post("/{workspace_id}/projects")
async def create_project(
    workspace_id: str,
    project_data: CreateProjectRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new project and notify members."""

    # Create project
    project = await project_service.create_project(...)

    # Get workspace members
    members = await get_workspace_members(workspace_id, db)

    # Notify all members
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    project_url = f"{frontend_url}/workspaces/{workspace_id}/projects/{project.id}"

    for member in members:
        background_tasks.add_task(
            send_workspace_email,
            db=db,
            email_type="project_created",
            workspace_id=UUID(workspace_id),
            recipient_email=member.email,
            user_id=member.user_id,  # For preferences check
            workspace_name=workspace.name,
            project_name=project.name,
            created_by_name=current_user["first_name"],
            project_url=project_url,
            frontend_url=frontend_url
        )

    return {"message": "Project created, notifications sent"}
```

### Step 6: Write Tests

**File**: `tests/unit/services/test_email_helpers.py`

```python
@pytest.mark.asyncio
async def test_send_project_created_email(mock_db, sample_workspace_id, sample_user_id):
    """Test project created notification."""
    with patch('src.services.email_helpers.EmailService') as mock_service, \
         patch('src.services.email_helpers.create_project_created_email') as mock_template:

        # Setup mocks
        mock_template.return_value = "<html>Project Created</html>"
        mock_email_service_instance = Mock()
        mock_email_service_instance.send_email = AsyncMock()
        mock_service.return_value = mock_email_service_instance

        # Call function
        result = await send_workspace_email(
            db=mock_db,
            email_type="project_created",
            workspace_id=sample_workspace_id,
            recipient_email="member@example.com",
            user_id=sample_user_id,
            workspace_name="Acme Inc",
            project_name="New Project",
            created_by_name="John Doe",
            project_url="https://app.wrext.com/projects/123"
        )

        # Assertions
        assert result is True
        mock_template.assert_called_once()
```

---

## Modifying Existing Templates

### Example: Update Welcome Email

**File**: `emails/templates/auth/welcome.py`

```python
def create_welcome_email(
    user_name: str,
    frontend_url: str = "https://app.wrext.com"
) -> str:
    """Render welcome email template."""

    # Modify content here
    email_html = compose_email([
        simple_header("Welcome to WREXT!"),
        f"""
        <h1>Welcome {user_name}! 👋</h1>
        <p>We're excited to have you on board.</p>

        <!-- ADD NEW CONTENT HERE -->
        <div style="background: #f3f4f6; padding: 16px; border-radius: 8px;">
            <h3>Quick Start Guide:</h3>
            <ol>
                <li>Create your first workspace</li>
                <li>Invite team members</li>
                <li>Start collaborating</li>
            </ol>
        </div>
        """,
        primary_button("Get Started", f"{frontend_url}/dashboard"),
        simple_footer()
    ])

    return email_html
```

**No code changes needed** - template modifications are automatically used.

### Testing Template Changes

```bash
# Run template preview server
python -m emails.examples.auth_templates_test

# Or use the preview API
curl http://localhost:8000/api/v1/email/preview/auth/welcome \
  -d '{"user_name": "Test User"}'
```

---

## Testing Email Flows

### Unit Testing

```python
# tests/unit/services/test_email_helpers.py
import pytest
from unittest.mock import AsyncMock, Mock, patch

@pytest.mark.asyncio
async def test_send_verification_email():
    """Test verification email sending."""
    with patch('src.services.email_helpers.EmailService') as mock_service:
        mock_service.return_value.send_email = AsyncMock()

        result = await send_auth_email(
            db=mock_db,
            email_type="verification",
            recipient_email="test@example.com",
            user_name="Test User",
            user_id=uuid4(),
            token="test-token"
        )

        assert result is True
```

### Integration Testing

```python
# tests/integration/test_email_flows.py
@pytest.mark.asyncio
async def test_complete_registration_flow(async_db):
    """Test end-to-end registration with email."""
    # Create user
    user = await create_test_user(async_db)

    # Send verification email
    result = await send_auth_email(
        db=async_db,
        email_type="verification",
        recipient_email=user.email,
        user_name=user.first_name,
        user_id=user.id,
        token="test-token"
    )

    assert result is True

    # Verify email was logged
    email_log = await async_db.execute(
        select(EmailLog).where(EmailLog.to_email == user.email)
    )
    assert email_log.scalar_one_or_none() is not None
```

### Manual Testing with Preview API

```bash
# 1. Start server
uvicorn src.api.server:app --reload

# 2. Preview auth emails
curl -X POST http://localhost:8000/api/v1/email/preview/auth/verification \
  -H "Content-Type: application/json" \
  -d '{
    "user_name": "Test User",
    "verification_token": "test123",
    "frontend_url": "http://localhost:3000"
  }'

# 3. Preview workspace emails
curl -X POST http://localhost:8000/api/v1/email/preview/workspace/invitation \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_name": "Acme Inc",
    "inviter_name": "Admin",
    "role_name": "Editor",
    "invitation_token": "inv123",
    "expiry_days": 7
  }'
```

---

## Troubleshooting

### Issue: Email Not Sending

**Symptoms**: Function returns `True` but no email received

**Debug Steps**:

1. **Check EmailService logs**:
```python
logger.setLevel(logging.DEBUG)
```

2. **Verify email_logs table**:
```sql
SELECT * FROM email_logs
WHERE to_email = 'test@example.com'
ORDER BY created_at DESC
LIMIT 5;
```

3. **Check provider status**:
```python
from src.services.email_service import EmailService
service = EmailService(db)
print(service.primary_provider.get_provider_name())
```

4. **Verify environment variables**:
```bash
echo $RESEND_API_KEY
echo $FRONTEND_URL
```

### Issue: Template Not Rendering

**Symptoms**: Blank or broken email content

**Debug Steps**:

1. **Test template directly**:
```python
from emails.templates.auth import create_verification_email

html = create_verification_email(
    user_name="Test",
    verification_token="token",
    frontend_url="http://localhost:3000"
)
print(len(html))  # Should be > 1000 bytes
print(html[:200])  # Preview first 200 chars
```

2. **Check for missing context variables**:
```python
# Make sure all required context is provided
await send_workspace_email(
    db=db,
    email_type="invitation",
    workspace_id=workspace_id,
    recipient_email=email,
    workspace_name=workspace.name,  # REQUIRED
    inviter_name=inviter.first_name,  # REQUIRED
    role_name=role.display_name,  # REQUIRED
    # ... all required fields
)
```

### Issue: Preferences Not Working

**Symptoms**: Emails sent despite user unsubscribing

**Debug Steps**:

1. **Verify preferences record exists**:
```sql
SELECT * FROM email_preferences WHERE user_id = 'user_uuid';
```

2. **Check preference value**:
```sql
SELECT workspace_invitation, role_changed
FROM email_preferences
WHERE user_id = 'user_uuid';
```

3. **Ensure user_id is passed**:
```python
# ✅ GOOD
await send_workspace_email(
    ...,
    user_id=member.user_id  # Must be provided
)

# ❌ BAD
await send_workspace_email(
    ...
    # Missing user_id - preferences not checked
)
```

---

## Advanced Topics

### Custom Email Provider

To add a new email provider (e.g., SendGrid):

1. **Create provider class**:
```python
# src/providers/email/sendgrid_provider.py
from src.providers.email.base import BaseEmailProvider, EmailMessage, EmailResult

class SendGridProvider(BaseEmailProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = sendgrid.SendGridAPIClient(api_key)

    async def send_email(self, message: EmailMessage) -> EmailResult:
        # Implement SendGrid sending logic
        pass

    def get_provider_name(self) -> str:
        return "sendgrid"
```

2. **Register in factory**:
```python
# src/providers/email/factory.py
from src.providers.email.sendgrid_provider import SendGridProvider

def get_email_provider() -> BaseEmailProvider:
    provider = os.getenv("EMAIL_PROVIDER", "resend")

    if provider == "sendgrid":
        return SendGridProvider(api_key=os.getenv("SENDGRID_API_KEY"))
    elif provider == "resend":
        return ResendProvider(api_key=os.getenv("RESEND_API_KEY"))
    # ...
```

### Database Email Templates

For workspace-customizable emails, use DB templates:

```python
# src/api/models/workspace_models/email_template.py
async def render_workspace_email(
    workspace_id: str,
    email_type: str,
    context: dict,
    db: AsyncSession
) -> dict:
    """Render email using workspace's custom template."""
    # Query custom template from database
    template = await get_workspace_template(workspace_id, email_type, db)

    if template:
        # Render custom template
        html = render_jinja_template(template.html_content, context)
        return {"subject": template.subject, "html": html}
    else:
        # Fallback to default Python template
        raise Exception("No custom template - use Python fallback")
```

---

## Code Style Guidelines

### Email Helper Usage

```python
# ✅ GOOD - Clear, explicit parameters
await send_auth_email(
    db=db,
    email_type="verification",
    recipient_email=user.email,
    user_name=user.first_name,
    user_id=user.id,
    token=verification_token,
    frontend_url=os.getenv("FRONTEND_URL"),
    background_tasks=background_tasks
)

# ❌ BAD - Unclear, missing parameters
send_email(user.email, "verify", token)
```

### Error Handling

```python
# ✅ GOOD - Log but don't raise
success = await send_auth_email(...)
if not success:
    logger.warning(f"Email failed to {recipient}")

# ❌ BAD - Don't raise exceptions for email failures
if not await send_auth_email(...):
    raise Exception("Email failed")  # DON'T DO THIS
```

### Background Tasks

```python
# ✅ GOOD - Use background tasks in production
background_tasks.add_task(
    send_workspace_email,
    db=db,
    ...
)

# ⚠️ ACCEPTABLE - Direct await only for testing
await send_workspace_email(
    db=db,
    ...,
    background_tasks=None  # Only in tests
)
```

---

## Resources

- **API Documentation**: `/docs/EMAIL_API_DOCUMENTATION.md`
- **Implementation Report**: `/EMAIL_SYSTEM_IMPLEMENTATION_FINAL_REPORT.md`
- **Code**: `src/services/email_helpers.py`
- **Tests**: `tests/unit/services/test_email_helpers.py`
- **Templates**: `emails/templates/`

---

**Questions?** Contact the backend team or open an issue in the repository.

**Last Updated**: October 12, 2025
