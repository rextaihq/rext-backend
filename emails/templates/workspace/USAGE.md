## Workspace Email Templates - Usage Guide

This guide shows how to integrate workspace email templates with existing invitation and workspace management routes.

## Templates

1. **Workspace Invitation** - Sent when inviting someone to join a workspace
2. **Invitation Accepted** - Sent to admins when someone accepts an invitation
3. **Role Changed** - Sent to member when their role is updated
4. **Member Removed** - Sent to member when they're removed from workspace

## Integration with Existing Routes

### 1. Workspace Invitation

**File:** `rext-backend/src/api/routes/workspaces/workspace_invitations.py`

**Current Implementation:**
```python
from src.utils.email_template_utils import render_workspace_email

email_content = render_workspace_email(
    db=db,
    workspace_id=workspace.id,
    template_type="workspace_invitation",
    variables={...}
)
background_tasks.add_task(
    send_email,
    to=invitation.email,
    subject=email_content["subject"],
    body=email_content["body"]
)
```

**New Implementation with Template:**
```python
from emails.templates.workspace import create_workspace_invitation_email
from src.services.email_service import EmailService
import os

# Get frontend URL
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Generate professional email HTML
email_html = create_workspace_invitation_email(
    workspace_name=workspace.name,
    inviter_name=inviter.display_name if inviter else "A teammate",
    invitation_token=invitation.invitation_token,
    role_name=role.display_name or role.name,
    expiry_days=payload.expiry_days or 7,
    workspace_description=workspace.description,  # Optional
    frontend_url=frontend_url
)

# Send via EmailService with tracking
email_service = EmailService(db)

async def send_invitation_email():
    await email_service.send_email(
        to=invitation.email,
        subject=f"You've been invited to join {workspace.name}",
        html=email_html,
        workspace_id=workspace.id,
        user_id=invitation.invited_by_user_id,
        template_type="workspace_invitation",
        tags={
            "type": "workspace",
            "action": "invitation",
            "role": role.name
        }
    )

background_tasks.add_task(send_invitation_email)
```

### 2. Invitation Accepted Notification

**Implementation:**
```python
from emails.templates.workspace import create_invitation_accepted_email
from src.services.email_service import EmailService
import os

# After accepting invitation in accept route
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Get workspace admins/owner to notify
admins = await get_workspace_admins(db, workspace_id)

# Generate email HTML
email_html = create_invitation_accepted_email(
    workspace_name=workspace.name,
    new_member_name=user.display_name or user.username,
    new_member_email=user.email,
    role_name=role.display_name or role.name,
    workspace_id=str(workspace.id),
    frontend_url=frontend_url
)

# Send to all admins
email_service = EmailService(db)

for admin in admins:
    background_tasks.add_task(
        email_service.send_email,
        to=admin.email,
        subject=f"New member joined {workspace.name}",
        html=email_html,
        workspace_id=workspace.id,
        user_id=admin.id,
        template_type="invitation_accepted",
        tags={
            "type": "workspace",
            "action": "member_joined",
            "new_member_id": str(user.id)
        }
    )
```

### 3. Role Changed Notification

**Implementation:**
```python
from emails.templates.workspace import create_role_changed_email
from src.services.email_service import EmailService
import os

# In update member role route
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Generate email HTML
email_html = create_role_changed_email(
    workspace_name=workspace.name,
    member_name=member.display_name or member.username,
    old_role_name=old_role.display_name,
    new_role_name=new_role.display_name,
    changed_by_name=current_user_name,
    workspace_id=str(workspace.id),
    frontend_url=frontend_url
)

# Send to affected member
email_service = EmailService(db)
background_tasks.add_task(
    email_service.send_email,
    to=member.email,
    subject=f"Your role in {workspace.name} has been updated",
    html=email_html,
    workspace_id=workspace.id,
    user_id=member.id,
    template_type="role_changed",
    tags={
        "type": "workspace",
        "action": "role_change",
        "old_role": old_role.name,
        "new_role": new_role.name
    }
)
```

### 4. Member Removed Notification

**Implementation:**
```python
from emails.templates.workspace import create_member_removed_email
from src.services.email_service import EmailService
import os

# In remove member route
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Generate email HTML
email_html = create_member_removed_email(
    workspace_name=workspace.name,
    member_name=removed_member.display_name or removed_member.username,
    removed_by_name=current_user_name,
    reason=removal_reason,  # Optional from request payload
    frontend_url=frontend_url
)

# Send to removed member
email_service = EmailService(db)
background_tasks.add_task(
    email_service.send_email,
    to=removed_member.email,
    subject=f"Removed from {workspace.name}",
    html=email_html,
    workspace_id=workspace.id,
    user_id=removed_member.id,
    template_type="member_removed",
    tags={
        "type": "workspace",
        "action": "member_removed",
        "removed_by": str(current_user_id)
    }
)
```

## Complete Example: Update Invitation Route

**File:** `rext-backend/src/api/routes/workspaces/workspace_invitations.py`

```python
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.database import get_async_db
from src.services.invitation_service import InvitationService
from src.services.email_service import EmailService
from emails.templates.workspace import create_workspace_invitation_email
import os

router = APIRouter()

@router.post("/{workspace_id}/invitations")
async def create_workspace_invitation(
    workspace_id: str,
    payload: InvitationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Create workspace invitation and send email."""
    user_uuid = UUID(str(user.get("identity")))

    # Get workspace and role
    workspace = await get_workspace(db, workspace_id)
    role = await get_role(db, payload.role_id)

    # Create invitation
    service = InvitationService(db)
    invitation = await service.create_invitation(
        email=payload.email,
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=user_uuid,
        expiry_days=payload.expiry_days or 7
    )

    # Get inviter info
    inviter = await get_user(db, user_uuid)

    # Get frontend URL
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Generate professional invitation email
    email_html = create_workspace_invitation_email(
        workspace_name=workspace.name,
        inviter_name=inviter.display_name if inviter else "A teammate",
        invitation_token=invitation.invitation_token,
        role_name=role.display_name or role.name,
        expiry_days=payload.expiry_days or 7,
        workspace_description=workspace.description,
        frontend_url=frontend_url
    )

    # Send via EmailService
    email_service = EmailService(db)

    async def send_invitation():
        await email_service.send_email(
            to=invitation.email,
            subject=f"You've been invited to join {workspace.name}",
            html=email_html,
            workspace_id=workspace.id,
            user_id=invitation.invited_by_user_id,
            template_type="workspace_invitation",
            tags={
                "type": "workspace",
                "action": "invitation",
                "workspace_id": str(workspace.id),
                "role": role.name
            }
        )

    background_tasks.add_task(send_invitation)

    # Commit and return
    await db.commit()

    return created(
        data={"invitation": invitation.to_dict()},
        message="Invitation sent successfully"
    )
```

## Template Features

### All Templates Include:
- ✅ Workspace-specific branding with workspace name in header
- ✅ Clear information hierarchy
- ✅ Professional design with proper spacing
- ✅ Responsive 600px layout
- ✅ Email client compatibility
- ✅ Preview text for inbox display
- ✅ Fallback text links for buttons

### Specific Features:

**Invitation Email:**
- Role information prominently displayed
- Optional workspace description
- Expiration warning (customizable days)
- Inviter name for context
- Security note about unexpected invitations

**Invitation Accepted:**
- Celebration message with checkmark
- New member details (name, email, role)
- Quick action suggestions
- Link to view workspace members

**Role Changed:**
- Visual before/after comparison
- Promotion/demotion detection with appropriate messaging
- Emoji indicators (🎉 for promotion, 🔄 for change)
- Explanation of what changed
- Contact info for questions

**Member Removed:**
- Clear explanation with emoji warning
- Optional reason display
- List of what access was lost
- Support contact information
- Link to remaining workspaces
- Reassurance about other workspaces

## Benefits

### 1. Professional Appearance
- Modern, branded design
- Consistent with Rext AI identity
- Better than plain text emails

### 2. Better User Experience
- Clear action items
- Visual hierarchy
- Easy to scan and understand

### 3. Improved Communication
- Proper context and reasoning
- Security considerations
- Support resources

### 4. Analytics & Tracking
- Database logging via EmailService
- Email delivery status tracking
- Tags for categorization
- Workspace association

## Testing

### Test Individual Templates

```python
from emails.templates.workspace import create_workspace_invitation_email

# Generate test email
html = create_workspace_invitation_email(
    workspace_name="Test Workspace",
    inviter_name="John Doe",
    invitation_token="test_token_123",
    role_name="Editor",
    expiry_days=7,
    frontend_url="http://localhost:3000"
)

# Save for preview
with open("test_invitation.html", "w") as f:
    f.write(html)
```

### Run Test Suite

```bash
cd emails/examples
python3 workspace_templates_test.py
```

This generates all 4 workspace email examples for preview.

## Migration Checklist

- [ ] Import template functions in workspace routes
- [ ] Replace `render_workspace_email` with new templates
- [ ] Update `send_email` to use EmailService
- [ ] Add template_type and tags for tracking
- [ ] Test invitation flow end-to-end
- [ ] Test role change notifications
- [ ] Test member removal notifications
- [ ] Preview emails in multiple clients
- [ ] Update environment variables
- [ ] Deploy to staging
- [ ] Monitor email delivery
- [ ] Deploy to production

## Environment Variables

Required in `.env`:

```env
FRONTEND_URL=https://app.rext.com

# Email service (already configured in Phase 1)
EMAIL_PROVIDER=resend
RESEND_API_KEY=re_xxxxxxxxxxxxx
RESEND_FROM_EMAIL=noreply@rext.com
RESEND_FROM_NAME=Rext AI
```

## Next Steps

After implementing workspace templates:

1. **Phase 3, Task 3.4**: Add email preview endpoint
   - Create FastAPI route for previewing templates
   - Admin UI for testing emails

2. **Phase 5**: Complete migration
   - Update all workspace routes
   - Remove old `render_workspace_email` utility
   - Remove deprecated `send_mail.py`

3. **Phase 6**: Testing
   - End-to-end workspace flow tests
   - Email delivery tests
   - Multi-client compatibility tests

## Support

For questions or issues:
- Check [emails/README.md](../../README.md) for component docs
- Review [EmailService docs](../../../rext-backend/src/services/email_service.py)
- Test templates using `emails/examples/workspace_templates_test.py`
- Preview generated HTML files in browser
