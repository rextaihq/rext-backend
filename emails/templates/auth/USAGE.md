# Auth Email Templates - Usage Guide

This guide shows how to integrate the auth email templates with the existing authentication routes.

## Templates

1. **Email Verification** - Sent when user registers
2. **Password Reset** - Sent when user requests password reset
3. **Welcome Email** - Sent after email verification (optional)

## Integration with Existing Routes

### 1. Email Verification (Registration)

**File:** `rext-backend/src/api/routes/users/auth.py`

**Current Implementation:**
```python
from src.api.tasks.send_mail import send_email

background_tasks.add_task(
    send_email,
    to=new_user.email,
    subject="Verify Your Email Address",
    body=f"<p>Welcome {new_user.first_name}!</p>..."
)
```

**New Implementation with Template:**
```python
from emails.templates.auth import create_verification_email
from src.services.email_service import EmailService
import os

# Get frontend URL from environment
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Generate email HTML using template
email_html = create_verification_email(
    user_name=new_user.first_name or new_user.username,
    verification_token=verification_token,
    frontend_url=frontend_url
)

# Send via EmailService (new way)
email_service = EmailService(db)
background_tasks.add_task(
    email_service.send_email,
    to=new_user.email,
    subject="Verify Your Email Address - Rext AI",
    html=email_html,
    user_id=new_user.id,
    template_type="email_verification",
    tags={"type": "auth", "action": "verification"}
)
```

### 2. Password Reset

**Implementation:**
```python
from emails.templates.auth import create_password_reset_email
from src.services.email_service import EmailService
import os

# In password reset route
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Generate email HTML using template
email_html = create_password_reset_email(
    user_name=user.first_name or user.username,
    reset_token=reset_token,
    user_email=user.email,
    frontend_url=frontend_url
)

# Send via EmailService
email_service = EmailService(db)
background_tasks.add_task(
    email_service.send_email,
    to=user.email,
    subject="Reset Your Password - Rext AI",
    html=email_html,
    user_id=user.id,
    template_type="password_reset",
    tags={"type": "auth", "action": "password_reset"}
)
```

### 3. Welcome Email (After Verification)

**Implementation:**
```python
from emails.templates.auth import create_welcome_email
from src.services.email_service import EmailService
import os

# In email verification route (after successful verification)
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Generate welcome email HTML
email_html = create_welcome_email(
    user_name=user.first_name or user.username,
    frontend_url=frontend_url
)

# Send via EmailService
email_service = EmailService(db)
background_tasks.add_task(
    email_service.send_email,
    to=user.email,
    subject="Welcome to Rext AI!",
    html=email_html,
    user_id=user.id,
    template_type="welcome",
    tags={"type": "auth", "action": "welcome"}
)
```

## Complete Example: Update Registration Route

**File:** `rext-backend/src/api/routes/users/auth.py`

```python
from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.database import get_async_db
from src.services.auth_service import AuthService
from src.services.email_service import EmailService
from src.api.schema.user_schema import RegisterUser
from src.utils.response_utils import created
from emails.templates.auth import create_verification_email
import os

router = APIRouter()

@router.post("/register")
async def register_user(
    user: RegisterUser,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    """Register new user and send verification email."""

    # Register user
    auth_service = AuthService(db)
    new_user, verification_token = await auth_service.register_user(
        email=user.email,
        username=user.username,
        password=user.password,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Get frontend URL from environment
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Generate verification email using template
    email_html = create_verification_email(
        user_name=new_user.first_name or new_user.username,
        verification_token=verification_token,
        frontend_url=frontend_url
    )

    # Send verification email via EmailService
    email_service = EmailService(db)

    async def send_verification():
        await email_service.send_email(
            to=new_user.email,
            subject="Verify Your Email Address - Rext AI",
            html=email_html,
            user_id=new_user.id,
            template_type="email_verification",
            tags={"type": "auth", "action": "verification"}
        )

    background_tasks.add_task(send_verification)

    # Commit transaction
    await db.commit()
    await db.refresh(new_user)

    # Return user data
    return created(
        data={"user": new_user.to_dict()},
        request=request,
        message="User created successfully. Please check your email to verify your account."
    )
```

## Benefits of Using Templates

### 1. Professional Design
- Modern, responsive layouts
- Consistent branding across all auth emails
- Email client compatibility (Gmail, Outlook, Apple Mail)

### 2. Better User Experience
- Clear call-to-action buttons
- Visual hierarchy and spacing
- Security notices and warnings
- Fallback text links

### 3. Maintainability
- Centralized template management
- Easy to update design/copy
- Type-safe with proper function signatures
- Testable and previewable

### 4. Tracking & Analytics
- Database logging via EmailService
- Email status tracking (sent, delivered, failed)
- Tags for categorization
- User ID association for analytics

## Template Customization

### Customize Per Workspace (Future)

```python
from emails.templates.auth import render_verification_email

# Custom verification URL with workspace branding
email_html = render_verification_email(
    user_name=user.first_name,
    verification_url=f"{frontend_url}/verify-email?token={token}&workspace={workspace_id}",
    frontend_url=frontend_url
)
```

### Override Frontend URL

```python
# Use different URL for staging/production
frontend_url = os.getenv("FRONTEND_URL", "https://app.rext.com")

email_html = create_verification_email(
    user_name="John",
    verification_token=token,
    frontend_url=frontend_url  # Use production URL
)
```

## Testing

### Test Email Generation

```python
from emails.templates.auth import create_verification_email

# Generate test email
html = create_verification_email(
    user_name="Test User",
    verification_token="test_token_123",
    frontend_url="http://localhost:3000"
)

# Save to file for preview
with open("test_email.html", "w") as f:
    f.write(html)

# Open in browser to preview
```

### Test Email Sending

```python
from src.services.email_service import EmailService
from emails.templates.auth import create_verification_email

# In a test or route
email_service = EmailService(db)

email_html = create_verification_email(
    user_name="Test User",
    verification_token="test_token",
    frontend_url="http://localhost:3000"
)

# Send test email
await email_service.send_email(
    to="test@example.com",
    subject="Test Verification Email",
    html=email_html,
    template_type="email_verification",
    tags={"type": "test"}
)
```

## Migration Checklist

- [ ] Import new template functions in auth routes
- [ ] Replace old `send_email` calls with EmailService
- [ ] Update email subjects
- [ ] Add template_type and tags for tracking
- [ ] Test in development environment
- [ ] Preview emails in multiple email clients
- [ ] Update environment variables (FRONTEND_URL)
- [ ] Deploy to staging
- [ ] Monitor email delivery rates
- [ ] Deploy to production

## Environment Variables

Ensure these are set in `.env`:

```env
# Frontend URL for email links
FRONTEND_URL=https://app.rext.com

# Email service configuration (already set in Phase 1)
EMAIL_PROVIDER=resend
RESEND_API_KEY=re_xxxxxxxxxxxxx
RESEND_FROM_EMAIL=noreply@rext.com
RESEND_FROM_NAME=Rext AI
```

## Troubleshooting

### Emails Not Rendering Correctly

1. Check that `FRONTEND_URL` is set correctly
2. Verify email HTML is being generated (print/log it)
3. Test in different email clients
4. Check EmailService logs in database

### Links Not Working

1. Verify `verification_token` is correct
2. Check frontend route matches (`/verify-email?token=...`)
3. Ensure token hasn't expired (24 hours default)

### Imports Failing

```python
# Make sure project root is in Python path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
```

## Next Steps

After implementing auth templates:

1. **Phase 3, Task 3.3**: Create workspace email templates
   - Workspace invitation
   - Invitation accepted
   - Role changed
   - Member removed

2. **Phase 3, Task 3.4**: Add email preview endpoint
   - Create FastAPI route for previewing templates
   - Admin UI integration

3. **Phase 5**: Migrate existing email functionality
   - Update all routes using old `send_email`
   - Remove deprecated `send_mail.py`
   - Update tests

## Support

For questions or issues:
- Check [emails/README.md](../../README.md) for component documentation
- Review [EmailService documentation](../../../src/services/email_service.py)
- Preview a template by rendering it as in the examples above and opening the saved HTML in a browser
