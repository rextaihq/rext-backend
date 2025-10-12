# Email Preview API Documentation

The Email Preview API allows you to generate and preview email templates before sending them. This is useful for:
- Testing email designs during development
- Previewing emails with different data
- Quality assurance before deployment
- Visual testing in different email clients

## Base URL

```
/api/v1/email/preview
```

## Authentication

All preview endpoints require authentication. Include a valid JWT token in the Authorization header:

```
Authorization: Bearer <your_token>
```

## Endpoints

### 1. Preview Auth Email (JSON Response)

Generate a preview of authentication email templates with full metadata.

**Endpoint:** `POST /api/v1/email/preview/auth`

**Request Body:**
```json
{
  "template_type": "verification",  // "verification", "password_reset", "welcome"
  "user_name": "John Doe",
  "user_email": "john@example.com",  // Optional, for password_reset
  "token": "preview_token_123",      // Optional, defaults provided
  "frontend_url": "https://app.wrext.com"  // Optional, uses env default
}
```

**Response:**
```json
{
  "html": "<!DOCTYPE html><html>...</html>",
  "template_type": "verification",
  "subject": "Verify Your Email Address - WREXT",
  "preview_text": "Welcome to WREXT! Verify your email to get started.",
  "metadata": {
    "template_name": "Auth - Verification",
    "size_bytes": 8192,
    "frontend_url": "https://app.wrext.com"
  }
}
```

**Examples:**

```bash
# Email Verification
curl -X POST http://localhost:8000/api/v1/email/preview/auth \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_type": "verification",
    "user_name": "John Doe"
  }'

# Password Reset
curl -X POST http://localhost:8000/api/v1/email/preview/auth \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_type": "password_reset",
    "user_name": "Jane Smith",
    "user_email": "jane@example.com"
  }'

# Welcome Email
curl -X POST http://localhost:8000/api/v1/email/preview/auth \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_type": "welcome",
    "user_name": "Alex"
  }'
```

### 2. Preview Workspace Email (JSON Response)

Generate a preview of workspace email templates with full metadata.

**Endpoint:** `POST /api/v1/email/preview/workspace`

**Request Body:**
```json
{
  "template_type": "invitation",  // "invitation", "invitation_accepted", "role_changed", "member_removed"
  "workspace_name": "Acme Corporation",
  "workspace_description": "Our main workspace",  // Optional
  "workspace_id": "workspace-uuid-123",  // Optional
  "user_name": "John Doe",
  "user_email": "john@example.com",  // Optional
  "secondary_user_name": "Jane Smith",  // Optional, for multi-user templates
  "role_name": "Editor",
  "old_role_name": "Viewer",  // For role_changed
  "invitation_token": "preview_token",  // Optional, defaults provided
  "expiry_days": 7,
  "reason": "Project concluded",  // For member_removed
  "frontend_url": "https://app.wrext.com"  // Optional
}
```

**Response:**
```json
{
  "html": "<!DOCTYPE html><html>...</html>",
  "template_type": "invitation",
  "subject": "You've been invited to join Acme Corporation",
  "preview_text": "You've been invited to join Acme Corporation on WREXT",
  "metadata": {
    "template_name": "Workspace - Invitation",
    "size_bytes": 9312,
    "workspace_name": "Acme Corporation",
    "frontend_url": "https://app.wrext.com"
  }
}
```

**Examples:**

```bash
# Workspace Invitation
curl -X POST http://localhost:8000/api/v1/email/preview/workspace \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_type": "invitation",
    "workspace_name": "Acme Corporation",
    "user_name": "John Doe",
    "role_name": "Editor",
    "expiry_days": 7
  }'

# Invitation Accepted
curl -X POST http://localhost:8000/api/v1/email/preview/workspace \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_type": "invitation_accepted",
    "workspace_name": "Acme Corporation",
    "user_name": "New Member",
    "secondary_user_name": "Jane Smith",
    "user_email": "jane@example.com",
    "role_name": "Editor"
  }'

# Role Changed
curl -X POST http://localhost:8000/api/v1/email/preview/workspace \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_type": "role_changed",
    "workspace_name": "Acme Corporation",
    "user_name": "Member Name",
    "old_role_name": "Viewer",
    "role_name": "Editor",
    "secondary_user_name": "Admin User"
  }'

# Member Removed
curl -X POST http://localhost:8000/api/v1/email/preview/workspace \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type": application/json" \
  -d '{
    "template_type": "member_removed",
    "workspace_name": "Acme Corporation",
    "user_name": "Member Name",
    "secondary_user_name": "Admin User",
    "reason": "Project concluded"
  }'
```

### 3. Preview Auth Email (HTML Response)

Get raw HTML for direct rendering in browser or iframe.

**Endpoint:** `POST /api/v1/email/preview/auth/html`

**Request Body:** Same as auth JSON endpoint

**Response:** Raw HTML email content

**Content-Type:** `text/html`

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/email/preview/auth/html \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_type": "verification",
    "user_name": "John Doe"
  }' > preview.html

# Open in browser
open preview.html
```

### 4. Preview Workspace Email (HTML Response)

Get raw HTML for direct rendering.

**Endpoint:** `POST /api/v1/email/preview/workspace/html`

**Request Body:** Same as workspace JSON endpoint

**Response:** Raw HTML email content

**Content-Type:** `text/html`

## Template Types

### Auth Templates

| Type | Description | Required Fields |
|------|-------------|-----------------|
| `verification` | Email verification after signup | `user_name` |
| `password_reset` | Password reset request | `user_name`, `user_email` (optional) |
| `welcome` | Welcome after email verification | `user_name` |

### Workspace Templates

| Type | Description | Required Fields |
|------|-------------|-----------------|
| `invitation` | Workspace invitation | `workspace_name`, `user_name`, `role_name` |
| `invitation_accepted` | Notification when someone joins | `workspace_name`, `user_name`, `user_email`, `role_name` |
| `role_changed` | Role update notification | `workspace_name`, `user_name`, `old_role_name`, `role_name`, `secondary_user_name` |
| `member_removed` | Removal notification | `workspace_name`, `user_name`, `secondary_user_name` |

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Unknown template type: invalid_type"
}
```

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to generate preview: [error message]"
}
```

## Usage Examples

### Python with requests

```python
import requests

API_URL = "http://localhost:8000/api/v1/email/preview"
TOKEN = "your_auth_token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Preview verification email
response = requests.post(
    f"{API_URL}/auth",
    headers=headers,
    json={
        "template_type": "verification",
        "user_name": "John Doe"
    }
)

data = response.json()
print(f"Subject: {data['subject']}")
print(f"Size: {data['metadata']['size_bytes']} bytes")

# Save HTML
with open("preview.html", "w") as f:
    f.write(data['html'])
```

### JavaScript/TypeScript

```typescript
const API_URL = 'http://localhost:8000/api/v1/email/preview';
const TOKEN = 'your_auth_token';

async function previewEmail() {
  const response = await fetch(`${API_URL}/auth`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      template_type: 'verification',
      user_name: 'John Doe'
    })
  });

  const data = await response.json();
  console.log(`Subject: ${data.subject}`);
  console.log(`Size: ${data.metadata.size_bytes} bytes`);

  // Display in iframe
  const iframe = document.getElementById('preview');
  iframe.srcdoc = data.html;
}
```

### Frontend Integration Example

```typescript
// React component for email preview
import { useState } from 'react';

function EmailPreview() {
  const [html, setHtml] = useState('');
  const [subject, setSubject] = useState('');

  const previewEmail = async () => {
    const response = await fetch('/api/v1/email/preview/auth/html', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        template_type: 'verification',
        user_name: 'Preview User'
      })
    });

    const htmlContent = await response.text();
    setHtml(htmlContent);
  };

  return (
    <div>
      <button onClick={previewEmail}>Preview Email</button>
      <div>
        <h3>Subject: {subject}</h3>
        <iframe
          srcDoc={html}
          style={{ width: '100%', height: '600px', border: '1px solid #ccc' }}
        />
      </div>
    </div>
  );
}
```

## Testing

### Using the Test Script

A test script is provided in `emails/examples/test_preview_endpoint.py`:

```bash
cd emails/examples

# Set your auth token in the script
# AUTH_TOKEN = "your_token_here"

python3 test_preview_endpoint.py
```

This will test all endpoints and generate preview HTML files.

### Manual Testing with cURL

```bash
# Get auth token first
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}' \
  | jq -r '.data.access_token')

# Preview email
curl -X POST http://localhost:8000/api/v1/email/preview/auth \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_type": "verification",
    "user_name": "Test User"
  }' | jq '.'
```

## Rate Limiting

Preview endpoints are subject to standard API rate limiting:
- 100 requests per minute per user
- 1000 requests per hour per user

## Security Considerations

1. **Authentication Required:** All endpoints require valid authentication
2. **User Context:** Preview endpoints can only be accessed by logged-in users
3. **No Email Sending:** Preview endpoints only generate HTML, they don't send emails
4. **Token Replacement:** Tokens in previews are replaced with example values
5. **Logging:** All preview requests are logged for audit purposes

## Best Practices

1. **Use JSON Endpoints for Metadata:** When you need subject, preview text, and size info
2. **Use HTML Endpoints for Display:** When rendering in iframe or browser
3. **Cache Previews:** Consider caching preview results on the frontend
4. **Test Different Clients:** Use generated HTML to test in various email clients
5. **Validate Before Production:** Always preview templates before deploying changes

## Integration with Email Service

Preview endpoints are separate from actual email sending:

```python
# Preview (no email sent)
preview = await preview_auth_email(request, current_user)

# Actual send (email sent via EmailService)
email_service = EmailService(db)
await email_service.send_email(
    to=user.email,
    subject=preview.subject,  # Can reuse subject from preview
    html=preview.html,        # Can reuse HTML from preview
    template_type="verification"
)
```

## Troubleshooting

### "Not authenticated" Error
- Ensure you're including a valid Bearer token
- Check token hasn't expired
- Verify token format: `Authorization: Bearer <token>`

### "Unknown template type" Error
- Check spelling of template_type
- Refer to Template Types section for valid values
- Ensure using correct endpoint (auth vs workspace)

### "Failed to generate preview" Error
- Check request body has all required fields
- Verify field values are valid (e.g., expiry_days 1-30)
- Check server logs for detailed error message

### Email Doesn't Render Correctly
- Some email clients have CSS limitations
- Test in multiple clients (Gmail, Outlook, Apple Mail)
- All templates use table-based layouts for compatibility

## API Reference

Full API documentation available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

Navigate to the "email-preview" tag to see all preview endpoints.

## Support

For issues or questions:
- Check [emails/README.md](README.md) for template documentation
- Review test script: `emails/examples/test_preview_endpoint.py`
- Check server logs for detailed error messages
- Contact backend team for API issues
