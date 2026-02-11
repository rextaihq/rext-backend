# Task 069: Hardcoded `http://localhost:3000` in Production Code

## Metadata
- **Task ID:** TASK-069
- **Source:** B3 - User Management (Finding #13 under P1 High)
- **Audit Report:** `audit-reports/backend-user-management.md`
- **Priority:** P1 High
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The invitation decline endpoint in `src/api/routes/users/invitations.py` contains a hardcoded `frontend_url="http://localhost:3000"` at line 340, accompanied by a `# TODO: Get from config` comment. This value is passed to the `create_invitation_declined_email` email template function, which uses it to construct URLs in the notification email sent to the user who originally created the invitation.

In production, this means that when a user declines a workspace invitation, the notification email sent to the inviter will contain links pointing to `http://localhost:3000` instead of the actual production frontend URL. These links will be unclickable or lead to nowhere for the recipient, creating a broken user experience and potentially raising trust/phishing concerns (recipients may perceive a localhost URL in an email as suspicious).

The application already has proper configuration infrastructure for this. The `Settings` class in `src/api/config.py` defines `FRONTEND_URL` as a configurable field (line 55) that defaults to `http://localhost:3000` but can be overridden via the `FRONTEND_URL` environment variable. Every other email template in the codebase correctly uses `settings.FRONTEND_URL` from this configuration. This single occurrence is an oversight where the developer left a hardcoded placeholder with a TODO that was never resolved.

---

## Current Code

```python
# File: rext-backend/src/api/routes/users/invitations.py
# Lines: 335-341
            # Generate email HTML
            email_html = create_invitation_declined_email(
                workspace_name=workspace.name,
                declined_by_email=user_email,
                decline_reason=decline_reason,
                workspace_id=str(workspace.id),
                frontend_url="http://localhost:3000"  # TODO: Get from config
            )
```

---

## Why This Matters (Context & Reasoning)

This code is part of the invitation decline flow. When a user receives a workspace invitation and declines it, the system sends an email notification to the person who invited them, informing them that the invitation was declined. The `frontend_url` parameter is used within the email template to generate clickable links (e.g., to the workspace dashboard).

In development, this works because the frontend runs on `http://localhost:3000`. In production, the actual frontend URL will be different (e.g., `https://app.rext.ai`). Without this fix, every invitation-declined email in production will have broken links, which degrades user trust and functionality.

The Twelve-Factor App methodology (Factor III) mandates that configuration that varies between deployments must be stored in the environment, not hardcoded in source code. This project already follows this pattern everywhere else via Pydantic `BaseSettings` — this is the one remaining violation in the user management routes.

---

## Impact

- **Severity:** Invitation declined notification emails contain broken localhost links in production. Users cannot click links in these emails to navigate back to the application.
- **Affected Users/Flows:** Any user who declines a workspace invitation — the inviter receives a broken email notification.
- **Blast Radius:** Isolated to the invitation decline email flow. Other email templates correctly use `settings.FRONTEND_URL`.

---

## Recommended Solution

### Step 1: Import settings at the top of the file

Check if `settings` or `get_settings` is already imported in `invitations.py`. If not, add the import.

```python
# File: rext-backend/src/api/routes/users/invitations.py
# Add near the top imports:
from src.api.config import settings
```

### Step 2: Replace the hardcoded URL with settings.FRONTEND_URL

```python
# File: rext-backend/src/api/routes/users/invitations.py
# Replace line 340:
# OLD: frontend_url="http://localhost:3000"  # TODO: Get from config
# NEW:
            email_html = create_invitation_declined_email(
                workspace_name=workspace.name,
                declined_by_email=user_email,
                decline_reason=decline_reason,
                workspace_id=str(workspace.id),
                frontend_url=settings.FRONTEND_URL
            )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-backend/src/config/payment_config.py` | `23-24` | Hardcoded `http://localhost:3000/checkout/success` and `http://localhost:3000/pricing` — same pattern but in billing scope (will be addressed in B5 extraction) |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Set the `FRONTEND_URL` environment variable to `https://app.example.com`
2. Create two test users. Have User A invite User B to a workspace.
3. Log in as User B and decline the invitation.
4. Check the email sent to User A — the links will point to `http://localhost:3000` instead of `https://app.example.com`.

### After Fix (Verify the Solution):
1. Set the `FRONTEND_URL` environment variable to `https://app.example.com`
2. Repeat the invitation decline flow.
3. Check the email sent to User A — the links should now point to `https://app.example.com`.
4. Also verify that with the default configuration (no env var set), the URL still defaults to `http://localhost:3000` for local development.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "invitation" -v
```

---

## Acceptance Criteria

- [ ] The hardcoded `"http://localhost:3000"` on line 340 of `invitations.py` is replaced with `settings.FRONTEND_URL`
- [ ] The `# TODO: Get from config` comment is removed
- [ ] The `settings` import is present at the top of the file
- [ ] Invitation declined emails use the configured `FRONTEND_URL` value
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Pydantic Settings Management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — how `BaseSettings` loads from environment variables
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [The Twelve-Factor App — Config](https://12factor.net/config) — configuration must be stored in the environment, not hardcoded
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-061 (`frontend_url` referenced before assignment in same codebase area)
